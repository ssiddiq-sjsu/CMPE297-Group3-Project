from amadeus import Client
from openai import OpenAI
import re, json, time, random
from datetime import datetime, timedelta
import requests

AMADEUS_CLIENT_ID = ""
AMADEUS_CLIENT_SECRET = ""
AMADEUS_BASE_URL = "https://test.api.amadeus.com"

# ---------- Clients ----------
amadeus = Client(client_id=AMADEUS_CLIENT_ID, client_secret=AMADEUS_CLIENT_SECRET)
openai_client = OpenAI()

# ---------- Mappings ----------
AIRPORT_TO_CITY_CODE = {
    "JFK": "NYC", "LGA": "NYC", "EWR": "NYC",
    "ORD": "CHI", "MDW": "CHI",
    "DCA": "WAS", "IAD": "WAS", "BWI": "WAS",
    "SFO": "SFO", "OAK": "SFO", "SJC": "SFO",
    "DFW": "DFW", "DAL": "DFW",
    "IAH": "HOU", "HOU": "HOU",
    "MIA": "MIA", "FLL": "MIA", "PBI": "MIA",
    "MCO": "ORL", "SFB": "ORL",
}

def resolve_hotel_city_code(destination_airport=None):
    if destination_airport:
        a = destination_airport.strip().upper()
        return AIRPORT_TO_CITY_CODE.get(a, a)
    return None

# ---------- Flights (SDK) ----------
def search_flights(origin, destination, date):
    response = amadeus.shopping.flight_offers_search.get(
        originLocationCode=origin,
        destinationLocationCode=destination,
        departureDate=date,
        adults=1,
        max=2
    )
    flights = []
    for offer in (response.data or []):
        flights.append({
            "price": offer["price"]["total"],
            "carrier": offer["itineraries"][0]["segments"][0]["carrierCode"],
            "duration": offer["itineraries"][0]["duration"]
        })
    return flights

# ---------- Hotels (REST) ----------
_token_cache = {"token": None, "expires_at": 0.0}

def amadeus_access_token():
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    url = f"{AMADEUS_BASE_URL}/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET,
    }
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    payload = r.json()
    _token_cache["token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 1800)) - 30
    return _token_cache["token"]

def amadeus_get(path, params=None, timeout=12, retries=2):
    token = amadeus_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AMADEUS_BASE_URL}{path}"

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.ok:
                return r.json()

            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep((0.6 * (2 ** attempt)) + random.random() * 0.3)
                continue

            return {"_error": {"status": r.status_code, "body": r.text}, "data": []}

        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                time.sleep((0.6 * (2 ** attempt)) + random.random() * 0.3)
                continue
            return {"_error": {"status": "timeout", "body": f"ReadTimeout after {timeout}s"}, "data": []}

        except requests.exceptions.RequestException as e:
            return {"_error": {"status": "request_exception", "body": str(e)}, "data": []}

def get_hotel_ids(city_code, max_ids=10):
    resp = amadeus_get("/v1/reference-data/locations/hotels/by-city", params={
        "cityCode": city_code,
        "radius": 10,
        "radiusUnit": "KM",
        "hotelSource": "ALL",
    }, timeout=10, retries=2)

    if resp.get("_error"):
        return []

    ids = []
    for h in (resp.get("data", []) or []):
        if isinstance(h, dict) and h.get("hotelId"):
            ids.append(h["hotelId"].strip())
    return ids[:max_ids]

def get_offers_for_hotel_ids(hotel_ids, check_in, check_out, adults=1, max_hotels=3):
    if not hotel_ids:
        return []

    offers = amadeus_get("/v3/shopping/hotel-offers", params={
        "hotelIds": ",".join([hid.strip() for hid in hotel_ids]),
        "checkInDate": check_in,
        "checkOutDate": check_out,
        "adults": adults,
        "roomQuantity": 1,
        "bestRateOnly": "true",
        "currency": "USD",
    }, timeout=12, retries=2)

    if offers.get("_error"):
        return []

    results = []
    for entry in (offers.get("data", []) or []):
        hotel = entry.get("hotel", {}) or {}
        offer_list = entry.get("offers", []) or []
        if not offer_list:
            continue
        offer = offer_list[0] or {}
        price = offer.get("price", {}) or {}
        results.append({
            "hotelId": hotel.get("hotelId"),
            "name": hotel.get("name"),
            "rating": hotel.get("rating"),
            "total": price.get("total"),
            "currency": price.get("currency"),
            "offerId": offer.get("id"),
        })

    def to_float(x):
        try: return float(x)
        except: return float("inf")
    results.sort(key=lambda r: to_float(r.get("total")))
    return results[:max_hotels]

# ---------- OpenAI parsing ----------
def parse_trip(user_input):
    prompt = f"""
        Extract flight search info from the text below.
        
        Rules:
        - Use IATA airport codes (SFO, LAX, JFK, LAS, etc.)
        - Convert relative dates like "next Monday" to YYYY-MM-DD
        - Return ONLY valid JSON
        
        JSON format:
        {{
          "origin": "IATA or null",
          "destination": "IATA or null",
          "flight_date": "YYYY-MM-DD or null"
        }}

    """
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    content = response.choices[0].message.content.strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {"origin": None, "destination": None, "flight_date": None}
    return json.loads(match.group())

def default_hotel_dates(flight_date_str, nights=2):
    d = datetime.fromisoformat(flight_date_str).date()
    return d.isoformat(), (d + timedelta(days=nights)).isoformat()

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_hotel_ids_by_city",
            "description": "Get valid Amadeus hotelIds for a given IATA city code (e.g., LAS, NYC, PAR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "city_code": {"type": "string", "description": "IATA city code, e.g. LAS, NYC"},
                    "max_ids": {"type": "integer", "description": "Max hotelIds to return", "default": 10}
                },
                "required": ["city_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hotel_offers",
            "description": "Get hotel offers/prices from Amadeus for provided hotelIds and dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hotel_ids": {"type": "array", "items": {"type": "string"}, "description": "List of hotelIds like NZLAS105"},
                    "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "YYYY-MM-DD"},
                    "adults": {"type": "integer", "default": 1},
                    "max_hotels": {"type": "integer", "default": 3}
                },
                "required": ["hotel_ids", "check_in", "check_out"]
            }
        }
    }
]

def run_tool_call(tc):
    name = tc.function.name
    args = json.loads(tc.function.arguments or "{}")

    if name == "get_hotel_ids_by_city":
        city_code = args["city_code"].strip().upper()
        max_ids = int(args.get("max_ids", 10))
        return {"city_code": city_code, "hotel_ids": get_hotel_ids(city_code, max_ids=max_ids)}

    if name == "get_hotel_offers":
        hotel_ids = [x.strip() for x in args.get("hotel_ids", []) if isinstance(x, str)]
        check_in = args["check_in"]
        check_out = args["check_out"]
        adults = int(args.get("adults", 1))
        max_hotels = int(args.get("max_hotels", 3))
        return {"hotels": get_offers_for_hotel_ids(hotel_ids, check_in, check_out, adults=adults, max_hotels=max_hotels)}

    return {"error": f"Unknown tool: {name}"}

# =========================
# Chat Loop (flights first, then tools for hotels)
# =========================
print("Travel Chatbot (type 'exit' to quit)\n")

messages = [{
    "role": "system",
    "content": (
        "You are a friendly travel consultant.\n"
        "Rules:\n"
        "- NEVER invent hotelIds. You must use tools to get hotelIds and hotel offers.\n"
        "- Always show hotel prices when available.\n"
        "- If hotel offers are empty, explain Amadeus sandbox may not return live prices.\n"
    )
}]

while True:
    user_input = input("You: ")
    if user_input.lower() == "exit":
        break

    trip = parse_trip(user_input)
    messages.append({"role": "user", "content": user_input})

    # If we have enough flight info, fetch flights + add hotel context for the model
    if trip.get("origin") and trip.get("destination") and trip.get("flight_date"):
        flights = search_flights(trip["origin"], trip["destination"], trip["flight_date"])
        check_in, check_out = default_hotel_dates(trip["flight_date"], nights=2)
        hotel_city = resolve_hotel_city_code(destination_airport=trip["destination"])

        context = {
            "trip": {
                "origin": trip["origin"],
                "destination_airport": trip["destination"],
                "flight_date": trip["flight_date"],
                "hotel_city_code": hotel_city,
                "check_in": check_in,
                "check_out": check_out
            },
            "flights": flights
        }

        messages.append({
            "role": "system",
            "content": (
                "Here is flight data and hotel search inputs.\n"
                "Next steps:\n"
                "1) Call get_hotel_ids_by_city using trip.hotel_city_code\n"
                "2) Then call get_hotel_offers using the returned hotel_ids and trip.check_in/check_out\n\n"
                + json.dumps(context, indent=2)
            )
        })

    # First model call
    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.3
    )
    msg = resp.choices[0].message
    messages.append(msg)

    # Handle tool calls until model stops calling tools
    while getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            tool_result = run_tool_call(tc)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(tool_result)
            })

        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3
        )
        msg = resp.choices[0].message
        messages.append(msg)
    print("User:", user_input)
    print("Bot:", msg.content)
