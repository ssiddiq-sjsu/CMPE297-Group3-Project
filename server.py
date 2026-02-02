"""
Vacation planning backend.
Serves the frontend and provides API endpoints backed by Python variables and stub functions.
"""
import json
from datetime import date
from flask import Flask, send_from_directory, request, jsonify

from config import PORT, HOST, DEBUG

app = Flask(__name__, static_folder="static")

# --- In-memory Python variables (no DB) ---
TRIPS = []  # List of trip dicts submitted by users
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
    'New York City',
    'Miami',
    'Los Angeles',
    'Orlando',
    'San Francisco',
    'Las Vegas',
    'Washington D.C.',
    'Chicago',
    'Honolulu',
    'Boston',
    'Vancouver',
    'Toronto',
    'Montreal',
    'San Diego', 
    'Seattle', 
    'New Orleans', 
    'Austin', 
    'Nashville', 
    'Savannah', 
    'Philadelphia', 
    'San Antonio', 
    'Denver', 
    'Charleston', 
    'Atlanta', 
    'Houston', 
    'Dallas'
]


# --- Stub / uncompleted functions (to be implemented later) ---
def search_flights(origin_code: str, destination: str, departure_date: str, return_date: str, budget_max: float):
    """Search for flights. Not implemented; returns placeholder."""
    # TODO: Integrate real flight API (e.g. Amadeus, Skyscanner)
    return None


def search_hotels(destination: str, check_in: str, check_out: str, budget_max: float):
    """Search for hotels. Not implemented; returns placeholder."""
    # TODO: Integrate hotel API
    return None


def search_activities(destination: str, activity_types: list[str], budget_max: float):
    """Search for activities based on selected types. Not implemented; returns placeholder."""
    # TODO: Integrate activities/experiences API
    return None


def build_trip_plan(trip_data: dict) -> str:
    """
    Build a text plan from trip data using the stub functions above.
    Actual processing is not implemented; returns a summary and placeholders.
    """
    flights = search_flights(
        trip_data.get("home_airport"),
        trip_data.get("destination"),
        trip_data.get("departure_date"),
        trip_data.get("return_date"),
        trip_data.get("budget", 0),
    )
    hotels = search_hotels(
        trip_data.get("destination"),
        trip_data.get("departure_date"),
        trip_data.get("return_date"),
        trip_data.get("budget", 0),
    )
    activities = search_activities(
        trip_data.get("destination"),
        trip_data.get("activity_types", []),
        trip_data.get("budget", 0),
    )

    prefer_red_eyes = trip_data.get("prefer_red_eyes", False)
    # Placeholder output until real APIs are connected
    lines = [
        f"Trip: {trip_data.get('destination', 'N/A')}",
        f"From: {trip_data.get('home_airport', 'N/A')}",
        f"Depart: {trip_data.get('departure_date', 'N/A')} — Return: {trip_data.get('return_date', 'N/A')}",
        f"Budget: ${trip_data.get('budget', 0):,.0f}",
        f"Prefer red-eye flights: {'Yes' if prefer_red_eyes else 'No'}",
        f"Activities: {', '.join(trip_data.get('activity_types', []) or ['None selected'])}",
        "",
        "--- Flights (not yet implemented) ---",
        "No flight results until search_flights() is implemented.",
        "",
        "--- Hotels (not yet implemented) ---",
        "No hotel results until search_hotels() is implemented.",
        "",
        "--- Activities (not yet implemented) ---",
        "No activity results until search_activities() is implemented.",
    ]
    return "\n".join(lines)


# --- Routes ---
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
    departure = data.get("departure_date", "") or ""
    return_date = data.get("return_date", "") or ""
    today = date.today()
    try:
        dep_d = date.fromisoformat(departure) if departure else None
        ret_d = date.fromisoformat(return_date) if return_date else None
    except ValueError:
        dep_d = ret_d = None
    if dep_d is not None and dep_d < today:
        return jsonify({
            "success": False,
            "message": "Departure and return dates must be today or in the future.",
        }), 400
    if ret_d is not None and ret_d < today:
        return jsonify({
            "success": False,
            "message": "Departure and return dates must be today or in the future.",
        }), 400
    if departure and return_date and departure >= return_date:
        return jsonify({
            "success": False,
            "message": "Return date must be after departure date.",
        }), 400
    trip_data = {
        "home_airport": data.get("home_airport", ""),
        "departure_date": departure,
        "destination": data.get("destination", ""),
        "return_date": return_date,
        "budget": float(data.get("budget", 0)),
        "activity_types": list(data.get("activity_types", [])),
        "prefer_red_eyes": bool(data.get("prefer_red_eyes", False)),
    }
    TRIPS.append(trip_data)
    output_text = build_trip_plan(trip_data)
    return jsonify({"success": True, "output": output_text, "trip_id": len(TRIPS)})


def main():
    print(f"Starting vacation planning server at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
