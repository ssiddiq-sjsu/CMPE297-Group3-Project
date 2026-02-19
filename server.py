"""
Vacation planning backend.
Serves frontend and provides API endpoints.
"""

from datetime import date
from flask import Flask, send_from_directory, request, jsonify

from config import PORT, HOST, DEBUG
from hotels_bot import search_hotels_for_trip
from flights_bot import search_flights_sdk, resolve_destination_airport

app = Flask(__name__, static_folder="static")

TRIPS = []

PRESET_AIRPORTS = [
    {"code": "SFO", "name": "San Francisco (SFO)"},
    {"code": "LAX", "name": "Los Angeles (LAX)"},
    {"code": "JFK", "name": "New York JFK (JFK)"},
    {"code": "ORD", "name": "Chicago O'Hare (ORD)"},
    {"code": "DFW", "name": "Dallas/Fort Worth (DFW)"},
    {"code": "SEA", "name": "Seattle (SEA)"},
    {"code": "MIA", "name": "Miami (MIA)"},
    {"code": "DEN", "name": "Denver (DEN)"},
    {"code": "ATL", "name": "Atlanta (ATL)"},
    {"code": "BOS", "name": "Boston (BOS)"},
]

PRESET_DESTINATIONS = [
    "New York City", "Miami", "Los Angeles", "Orlando", "San Francisco",
    "Las Vegas", "Washington D.C.", "Chicago", "Honolulu", "Boston",
    "Vancouver", "Toronto", "Montreal", "San Diego", "Seattle", "New Orleans",
    "Austin", "Nashville", "Savannah", "Philadelphia", "San Antonio", "Denver",
    "Charleston", "Atlanta", "Houston", "Dallas"
]


def search_flights(origin_code: str, destination: str, departure_date: str, return_date: str, budget_max: float):
    """
    Flight search using Amadeus SDK (one-way).
    origin_code: IATA airport code (from UI)
    destination: GUI label or airport code
    """
    if not origin_code or not destination or not departure_date:
        return []

    dest_airport = resolve_destination_airport(destination)
    if not dest_airport:
        return []

    flights = search_flights_sdk(
        origin=origin_code,
        destination=dest_airport,
        departure_date=departure_date,
        adults=1,
        max_results=3,
        currency="USD",
    )

    # Filter by budget if a positive budget was provided (budget_max=0 means no filter)
    if not budget_max:
        return flights

    filtered = []
    for f in flights:
        try:
            price_val = float(f.get("price_raw") or 0)
            if price_val <= float(budget_max):
                filtered.append(f)
        except Exception:
            filtered.append(f)
    return filtered


def search_hotels(destination: str, check_in: str, check_out: str, budget_max: float):
    try:
        return search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=1,
            max_hotels=3,
        )
    except Exception:
        return []


def search_activities(destination: str, activity_types: list[str], budget_max: float):
    return []


def build_trip_plan(trip_data: dict, flights: list, hotels: list) -> str:
    """
    Build a human-readable trip summary using the already formatted flight/hotel entries.
    flights: list of dicts returned by search_flights()
    hotels: list of dicts returned by search_hotels()
    """
    lines = [
        f"Trip: {trip_data.get('destination', 'N/A')}",
        f"From: {trip_data.get('home_airport', 'N/A')}",
        f"Depart: {trip_data.get('departure_date', 'N/A')} — Return: {trip_data.get('return_date', 'N/A')}",
        f"Budget: ${trip_data.get('budget', 0):,.0f}",
        f"Prefer red-eye flights: {'Yes' if trip_data.get('prefer_red_eyes') else 'No'}",
        f"Activities: {', '.join(trip_data.get('activity_types', []) or ['None selected'])}",
        "",
        "--- Flights ---",
    ]

    if not flights:
        lines.append("No flight offers found (Amadeus sandbox can be limited, and credentials must be set).")
    else:
        for f in flights:
            # Example pretty block:
            # - United Airlines • SFO → LAX
            #   Depart: Apr 8 • 9:35 PM
            #   Arrive: Apr 8 • 11:04 PM
            #   Duration: 1h 29m
            #   Price: $63.99
            lines.append(
                f"- {f.get('carrier', 'Unknown Carrier')} • {f.get('from', '')} → {f.get('to', '')}"
            )
            lines.append(f"  Depart: {f.get('departure')}")
            lines.append(f"  Arrive: {f.get('arrival')}")
            lines.append(f"  Duration: {f.get('duration')}")
            lines.append(f"  Price: {f.get('price')}")
            lines.append("")  # blank line between offers

    lines.append("--- Hotels ---")
    if not hotels:
        lines.append("No hotel offers found (Amadeus sandbox can be limited, and credentials must be set).")
    else:
        for h in hotels:
            lines.append(f"- {h.get('name','Unknown')} | Rating: {h.get('rating','N/A')}")
            lines.append(f"  Total: {h.get('total','N/A')} {h.get('currency','USD')}")
            lines.append("")

    lines.append("--- Activities ---")
    lines.append("Activities are not implemented yet.")

    return "\n".join(lines)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.route("/api/airports", methods=["GET"])
def api_airports():
    return jsonify(PRESET_AIRPORTS)


@app.route("/api/destinations", methods=["GET"])
def api_destinations():
    return jsonify(PRESET_DESTINATIONS)


@app.route("/api/trip", methods=["POST"])
def api_create_trip():
    data = request.get_json(force=True, silent=True) or {}

    departure = (data.get("departure_date") or "").strip()
    return_date = (data.get("return_date") or "").strip()

    today = date.today()
    try:
        dep_d = date.fromisoformat(departure) if departure else None
        ret_d = date.fromisoformat(return_date) if return_date else None
    except ValueError:
        dep_d = ret_d = None

    if dep_d is not None and dep_d < today:
        return jsonify({"success": False, "message": "Departure and return dates must be today or in the future."}), 400
    if ret_d is not None and ret_d < today:
        return jsonify({"success": False, "message": "Departure and return dates must be today or in the future."}), 400
    if departure and return_date and departure >= return_date:
        return jsonify({"success": False, "message": "Return date must be after departure date."}), 400

    trip_data = {
        "home_airport": data.get("home_airport", ""),
        "departure_date": departure,
        "destination": data.get("destination", ""),
        "return_date": return_date,
        "budget": float(data.get("budget", 0) or 0),
        "activity_types": list(data.get("activity_types", []) or []),
        "prefer_red_eyes": bool(data.get("prefer_red_eyes", False)),
    }

    TRIPS.append(trip_data)

    flights = search_flights(
        trip_data["home_airport"],
        trip_data["destination"],
        trip_data["departure_date"],
        trip_data["return_date"],
        trip_data["budget"],
    )

    hotels = search_hotels(
        trip_data["destination"],
        trip_data["departure_date"],
        trip_data["return_date"],
        trip_data["budget"],
    )

    output_text = build_trip_plan(trip_data, flights=flights, hotels=hotels)

    return jsonify({
        "success": True,
        "output": output_text,
        "flights": flights,
        "hotels": hotels,
        "trip_id": len(TRIPS),
    })


def main():
    print(f"Starting server at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
