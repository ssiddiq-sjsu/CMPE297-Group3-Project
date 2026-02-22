"""
Amadeus flight search: resolve city to IATA and query flight offers.
Uses AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET (or AMADEUS_API_KEY as client_id) from env.
"""
import os
import re
from datetime import datetime

from amadeus import Client

# Create client from env (API Key = client_id, API Secret = client_secret)
_client_id = os.getenv("AMADEUS_CLIENT_ID")
_client_secret = os.getenv("AMADEUS_SECRET")
if not _client_id or not _client_secret:
    _amadeus = None
    print("amadeus not initialized")
else:
    _amadeus = Client(client_id=_client_id, client_secret=_client_secret)
    print("amadeus initialized")


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (e.g. PT2H10M) to human-readable (e.g. 2h 10m)."""
    if not iso_duration:
        return "N/A"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
    if not m:
        return iso_duration
    h, mn = int(m.group(1) or 0), int(m.group(2) or 0)
    parts = []
    if h:
        parts.append(f"{h}h")
    if mn:
        parts.append(f"{mn}m")
    return " ".join(parts) if parts else "0m"


def _normalize_offer(offer: dict, origin_code: str, dest_code: str, direction: str) -> dict:
    """Turn one Amadeus flight offer into a single flight dict for the agent."""
    if not offer or not offer.get("itineraries"):
        return None
    itin = offer["itineraries"][0]
    segs = itin.get("segments") or []
    if not segs:
        return None
    seg = segs[0]
    dep = seg.get("departure") or {}
    arr = seg.get("arrival") or {}
    dep_at = dep.get("at", "")
    arr_at = arr.get("at", "")
    # Format datetimes for display (keep ISO if needed for API)
    try:
        dep_dt = datetime.fromisoformat(dep_at.replace("Z", "+00:00")) if dep_at else None
        arr_dt = datetime.fromisoformat(arr_at.replace("Z", "+00:00")) if arr_at else None
        dep_str = dep_dt.strftime("%Y-%m-%d %H:%M") if dep_dt else dep_at or "N/A"
        arr_str = arr_dt.strftime("%Y-%m-%d %H:%M") if arr_dt else arr_at or "N/A"
    except (ValueError, TypeError):
        dep_str = dep_at or "N/A"
        arr_str = arr_at or "N/A"
    duration = _parse_duration(itin.get("duration", ""))
    carrier = seg.get("carrierCode", "")
    number = seg.get("number", "")
    flight_number = f"{carrier}{number}" if carrier or number else "N/A"
    price = float((offer.get("price") or {}).get("total", 0))
    return {
        "home_airport": origin_code,
        "destination": dest_code,
        "departure_date": dep_str,
        "arrival_date": arr_str,
        "return_date": dep_str if direction == "return" else arr_str,
        "cost": price,
        "airline": carrier or "N/A",
        "duration": duration,
        "flight_number": flight_number,
        "direction": direction,
    }


def city_to_iata(city: str) -> str | None:
    """Resolve a city name to an IATA airport/city code using Amadeus."""
    if not _amadeus:
        print("amadeus not initialized")
        return None
    try:
        res = _amadeus.reference_data.locations.get(
            keyword=city,
            subType="AIRPORT,CITY",
        ) 
        if not res.data:
            print("no data in city_to_iata")
            return None
        print("city_to_iata result: ", res.data[0].get("iataCode"))
        if res.data and len(res.data) > 0:
            return res.data[0].get("iataCode")
    except Exception as e:
        print("error in city_to_iata: ", e)
        pass
    return None


def search_flights(origin_iata: str, destination_iata: str, date: str):
    """One-way flight offers search. Returns raw Amadeus response.data or []."""
    if not _amadeus:
        print("amadeus not initialized")
        return []
    try:
        response = _amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin_iata,
            destinationLocationCode=destination_iata,
            departureDate=date,
            adults=1,
            max=5,
        )
        print("search_flights result: ", response.data)
        return response.data or []
    except Exception:
        return []


def query_flights(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    prefer_red_eyes: bool = False,
    max_price: float | None = None,
) -> list[dict]:
    """
    Query Amadeus for flight offers (outbound and optionally return).
    destination can be IATA code or city name (resolved via city_to_iata).
    Returns a list of normalized flight dicts, each with:
    home_airport, destination, departure_date (with time), arrival_date, cost, airline, duration, flight_number, direction.
    """
    if not _amadeus:
        print("amadeus not initialized")
        return []
    print("\n\nquery_flights with arguments: ", origin_code, destination, departure_date, return_date, prefer_red_eyes, max_price)
    dest_iata = destination if len(destination) == 3 and destination.isupper() else city_to_iata(destination)
    print("\n\ndest_iata: ", dest_iata)
    if not dest_iata:
        dest_iata = destination
    outbound_raw = search_flights(origin_code, dest_iata, departure_date)
    print("outbound_raw: ", outbound_raw)
    flights = []
    for offer in outbound_raw:
        if max_price is not None and float((offer.get("price") or {}).get("total", 0)) > max_price:
            continue
        f = _normalize_offer(offer, origin_code, dest_iata, "outbound")
        if f:
            flights.append(f)
    if return_date:
        return_raw = search_flights(dest_iata, origin_code, return_date)
        for offer in return_raw:
            if max_price is not None and float((offer.get("price") or {}).get("total", 0)) > max_price:
                continue
            f = _normalize_offer(offer, dest_iata, origin_code, "return")
            if f:
                flights.append(f)
    if prefer_red_eyes:
        # Prefer departures between 21:00 and 05:00 (next day) local; we don't have timezone here, so sort by dep time string
        def red_eye_score(flight):
            dep = flight.get("departure_date", "") or ""
            if " " in dep:
                try:
                    t = datetime.strptime(dep.split(" ")[1][:5], "%H:%M")
                    h = t.hour + t.minute / 60
                    if h >= 21 or h < 5:
                        return 0
                    return 1
                except ValueError:
                    pass
            return 1
        flights.sort(key=lambda x: (red_eye_score(x), x.get("cost", 0)))
    else:
        flights.sort(key=lambda x: x.get("cost", 0))
    return flights
