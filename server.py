"""
Vacation planning backend.
Serves the frontend and provides API endpoints backed by Python variables and stub functions.
"""
import json
from datetime import date, timedelta
from flask import Flask, send_from_directory, request, jsonify

from config import PORT, HOST, DEBUG

app = Flask(__name__, static_folder="static")

# --- In-memory Python variables (no DB) ---
TRIPS = []  # List of trip dicts submitted by users
# Saved itineraries: key = user-provided name, value = plan dict (total_budget, flights, days)
SAVED_ITINERARIES = {}
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


def build_trip_plan(trip_data: dict) -> dict:
    """
    Build a structured plan from trip data. Populate the variables below;
    when stub APIs return real data, assign it here. Returns a dict for the frontend.
    """
    origin = trip_data.get("home_airport", "N/A")
    destination = trip_data.get("destination", "N/A")
    dep_date = trip_data.get("departure_date", "")
    ret_date = trip_data.get("return_date", "")
    total_budget = float(trip_data.get("budget", 0)) # should confirm if end budget is the same as total budget
    prefer_red_eyes = trip_data.get("prefer_red_eyes", False)
    activity_types = trip_data.get("activity_types") or []

    # --- Variables to be populated by stub / real APIs ---
    raw_flights = search_flights(origin, destination, dep_date, ret_date, total_budget)
    raw_hotels = search_hotels(destination, dep_date, ret_date, total_budget)
    raw_activities = search_activities(destination, activity_types, total_budget)

    # Flights: list of { "description": str, "cost": float }
    flights = []
    if raw_flights:
        for f in raw_flights:
            flights.append({
                "description": f.get("description", "Flight"),
                "cost": float(f.get("cost", 0)),
            })
    else:
        # Placeholder when search_flights() not implemented
        flights = [
            {"description": f"Outbound: {origin} → {destination} ({dep_date}) — placeholder", "cost": 0},
            {"description": f"Return: {destination} → {origin} ({ret_date}) — placeholder", "cost": 0},
        ]

    # Days: one entry per day of the trip; each has activities, hotel, other, daily_budget
    # Populate from raw_hotels / raw_activities when stubs return real data
    days = []
    try:
        dep_d = date.fromisoformat(dep_date) if dep_date else None
        ret_d = date.fromisoformat(ret_date) if ret_date else None
    except ValueError:
        dep_d = ret_d = None
    if dep_d and ret_d and dep_d < ret_d:
        day_count = (ret_d - dep_d).days + 1
        daily_budget_placeholder = round(total_budget / day_count, 2) if day_count else 0
        for i in range(day_count):
            d = dep_d + timedelta(days=i)
            date_str = d.isoformat()
            raw_hotel = raw_hotels[i] if raw_hotels and i < len(raw_hotels) else None
            raw_day_activities = raw_activities[i] if raw_activities and i < len(raw_activities) else None
            hotel_name = (raw_hotel.get("name") if isinstance(raw_hotel, dict) else raw_hotel) or "Hotel TBD"
            activity_list = list(raw_day_activities) if isinstance(raw_day_activities, list) else ["Activities TBD"]
            days.append({
                "date": date_str,
                "day_number": i + 1,
                "activities": activity_list,
                "hotel": hotel_name,
                "other": "",
                "daily_budget": daily_budget_placeholder,
            })
    else:
        days = [{
            "date": dep_date or "N/A",
            "day_number": 1,
            "activities": ["Activities TBD"],
            "hotel": "Hotel TBD",
            "other": "",
            "daily_budget": total_budget,
        }]

    return {
        "total_budget": total_budget,
        "flights": flights,
        "days": days,
    }


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
    plan = build_trip_plan(trip_data)
    return jsonify({"success": True, "plan": plan, "trip_id": len(TRIPS)})


@app.route("/api/itineraries", methods=["GET"])
def api_list_itineraries():
    """Return list of saved itinerary names."""
    return jsonify({"names": list(SAVED_ITINERARIES.keys())})


@app.route("/api/itineraries/save", methods=["POST"])
def api_save_itinerary():
    """Save a plan under the given name. Body: { "name": str, "plan": plan_dict }."""
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    plan = data.get("plan")
    if not name:
        return jsonify({"success": False, "message": "Name is required."}), 400
    if not plan or not isinstance(plan, dict):
        return jsonify({"success": False, "message": "Valid plan data is required."}), 400
    SAVED_ITINERARIES[name] = {
        "total_budget": plan.get("total_budget", 0),
        "flights": list(plan.get("flights", [])),
        "days": list(plan.get("days", [])),
    }
    return jsonify({"success": True, "name": name})


@app.route("/api/itineraries/<path:name>", methods=["GET"])
def api_get_itinerary(name):
    """Return saved plan for the given name (URL-decoded)."""
    plan = SAVED_ITINERARIES.get(name)
    if plan is None:
        return jsonify({"success": False, "message": "Itinerary not found."}), 404
    return jsonify({"success": True, "plan": plan})


def main():
    print(f"Starting vacation planning server at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
