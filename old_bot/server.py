"""
Vacation planning backend.
Serves the frontend and provides API endpoints backed by Python variables and stub functions.
"""
import json
import os
from datetime import date, timedelta

from flask import Flask, send_from_directory, request, jsonify
from dotenv import load_dotenv

from config import PORT, HOST, DEBUG

app = Flask(__name__, static_folder="static")

# --- In-memory Python variables (no DB) ---
TRIPS = []  # List of trip dicts submitted by users
# Saved itineraries: key = user-provided name, value = plan dict (total_budget, flights, days)
SAVED_ITINERARIES = {}
# Last plan and trip data for controller (so subsequent calls with extra_info get previous plan as context)
LAST_PLAN = None
LAST_TRIP_KEY = None
LAST_TRIP_DATA = None
PRESET_AIRPORTS = [
    {"code": "SFO", "name": "San Francisco (SFO)"},
    {"code": "LAX", "name": "Los Angeles (LAX)"},
    {"code": "JFK", "name": "New York JFK (JFK)"}, # Newark and Lagaurdia don't exist okay
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

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set")
# AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY")
# if not AMADEUS_API_KEY:
#     raise ValueError("AMADEUS_API_KEY is not set")
PHQ_API_KEY = os.getenv("PHQ_API_KEY")
if not PHQ_API_KEY:
    raise ValueError("PHQ_API_KEY is not set")


# --- Stub / uncompleted functions (to be implemented later) ---
def search_flights(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: str,
    budget_max: float,
    prefer_red_eyes: bool = False,
):
    """
    Search for flights via the ReAct agent (OpenAI + Amadeus).
    Returns a list of flight dicts with origin, destination, departure_date, arrival_date,
    cost, description, airline, duration, flight_number; or None on failure.
    """
    try:
        from bot.flights_bot import run_agent
        agent_flights = run_agent(
            origin_code=origin_code,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            budget_max=float(budget_max),
            prefer_red_eyes=prefer_red_eyes,
        )
        if not agent_flights:
            return None
        raw = []
        for f in agent_flights:
            origin = f.get("home_airport", "N/A")
            dest = f.get("destination", "N/A")
            dep = f.get("departure_date", "N/A")
            arr = f.get("arrival_date", "N/A")
            cost = float(f.get("cost", 0))
            airline = f.get("airline", "N/A")
            duration = f.get("duration", "N/A")
            fn = f.get("flight_number", "N/A")
            raw.append({
                "description": f"{airline} {fn}: {origin} → {dest} ({duration})",
                "origin": origin,
                "destination": dest,
                "departure_date": dep,
                "arrival_date": arr,
                "cost": cost,
                "airline": airline,
                "duration": duration,
                "flight_number": fn,
            })
        print("raw flights: ", raw)
        return raw
    except Exception:
        return None


def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    budget_max: float,
    extra_info: str = "",
):
    """
    Search for hotels via the hotel agent (OpenAI Agents SDK + Amadeus).
    Returns a list of hotel dicts with name, description, cost, location, type, rating
    (one per day, same hotel repeated), or None on failure.
    """
    try:
        from bot.hotels_bot import run_agent as run_hotel_agent
        hotels = run_hotel_agent(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            budget_max=float(budget_max),
            extra_info=extra_info or "",
        )
        print("hotels: ", hotels)
        if not hotels:
            return None
        # Server expects one hotel dict per day; we have one suggested hotel for the stay
        raw = []
        for h in hotels:
            raw.append({
                "name": h.get("name", "N/A"),
                "description": f"Hotel (rating: {h.get('rating', 'N/A')})",
                "cost": float(h.get("total", 0)),
                "location": destination,
                "type": "hotel",
                "rating": h.get("rating"),
            })
        return raw
    except Exception:
        return None


def search_activities(
        destination: str, 
        activity_types: list[str], 
        budget_max: float,
        start_date: str = "",
        end_date: str = ""
        ):
    """Search for activities via PredictHQ agent
    Returns per-day list of activity name lists"""
    try:
        from bot.events_bot import run_agent
        return run_agent(
            destination=destination,
            start_date=start_date,
            end_date=end_date,
            activity_types=list(activity_types or []),
            budget_max=float(budget_max)
        )
    except Exception:
        return None


def handle_additional_info(info: str):
    """
    Process user-provided additional information. If a plan has been created,
    passes the info to the controller to update the plan and returns the new plan.
    If no plan exists or update fails, returns None (and prints an error when no plan).
    """
    if not info or not info.strip():
        return None
    global LAST_PLAN, LAST_TRIP_DATA
    if LAST_PLAN is None or LAST_TRIP_DATA is None:
        print("Error: No plan exists yet. Create a trip first before submitting additional info.")
        return None
    try:
        from bot.controller_bot import run_controller
        trip_data_with_info = {**LAST_TRIP_DATA, "extra_info": info.strip()}
        plan = run_controller(LAST_PLAN, trip_data_with_info)
        LAST_PLAN = plan
        return plan
    except Exception as e:
        print("Error updating plan with additional info:", e)
        return None



def _trip_key(trip_data: dict) -> tuple:
    """Key for same-trip detection (origin, destination, dates, budget)."""
    return (
        str(trip_data.get("home_airport", "")).strip(),
        str(trip_data.get("destination", "")).strip(),
        str(trip_data.get("departure_date", "")).strip(),
        str(trip_data.get("return_date", "")).strip(),
        float(trip_data.get("budget", 0)),
    )


def build_trip_plan(trip_data: dict) -> dict:
    """
    Build a structured plan from trip data using the controller agent.
    Controller calls flights and hotels bots and returns a plan for the frontend.
    On first call current_plan is empty; on subsequent calls with same trip + extra_info
    the controller receives the previous plan and session context to update the plan.
    """
    global LAST_PLAN, LAST_TRIP_KEY, LAST_TRIP_DATA
    try:
        from bot.controller_bot import run_controller
        trip_key = _trip_key(trip_data)
        current_plan = LAST_PLAN if (LAST_TRIP_KEY is not None and LAST_TRIP_KEY == trip_key) else {}
        plan = run_controller(current_plan, trip_data)
        LAST_PLAN = plan
        LAST_TRIP_KEY = trip_key
        LAST_TRIP_DATA = trip_data
        return plan
    except Exception as e:
        print("error building trip plan: ", e)
        # LAST_PLAN = None
        # LAST_TRIP_KEY = None
        # # Fallback: build plan without controller (original logic)
        # origin = trip_data.get("home_airport", "N/A")
        # destination = trip_data.get("destination", "N/A")
        # dep_date = trip_data.get("departure_date", "")
        # ret_date = trip_data.get("return_date", "")
        # total_budget = float(trip_data.get("budget", 0))
        # prefer_red_eyes = trip_data.get("prefer_red_eyes", False)
        # activity_types = trip_data.get("activity_types") or []
        # raw_flights = search_flights(origin, destination, dep_date, ret_date, total_budget, prefer_red_eyes=prefer_red_eyes)
        # raw_hotels = search_hotels(destination, dep_date, ret_date, total_budget, extra_info=trip_data.get("extra_info", ""))
        # raw_activities = search_activities(destination, activity_types, total_budget)
        # flights = []
        # if raw_flights:
        #     for f in raw_flights:
        #         flights.append({
        #             "description": f.get("description", "Flight"),
        #             "origin": f.get("origin", "N/A"),
        #             "destination": f.get("destination", "N/A"),
        #             "departure_date": f.get("departure_date", "N/A"),
        #             "arrival_date": f.get("arrival_date", "N/A"),
        #             "cost": float(f.get("cost", 0)),
        #         })
        # else:
        #     flights = [
        #         {"description": f"Outbound: {origin} → {destination} ({dep_date}) — placeholder", "origin": origin, "destination": destination, "departure_date": dep_date, "arrival_date": dep_date, "cost": 0},
        #         {"description": f"Return: {destination} → {origin} ({ret_date}) — placeholder", "origin": destination, "destination": origin, "departure_date": ret_date, "arrival_date": ret_date, "cost": 0},
        #     ]
        # days = []
        # try:
        #     dep_d = date.fromisoformat(dep_date) if dep_date else None
        #     ret_d = date.fromisoformat(ret_date) if ret_date else None
        # except ValueError:
        #     dep_d = ret_d = None
        # if dep_d and ret_d and dep_d < ret_d:
        #     day_count = (ret_d - dep_d).days + 1
        #     for i in range(day_count):
        #         daily_budget = 0
        #         d = dep_d + timedelta(days=i)
        #         date_str = d.isoformat()
        #         raw_hotel = raw_hotels[min(i, len(raw_hotels) - 1)] if raw_hotels else None
        #         raw_day_activities = raw_activities[i] if raw_activities and i < len(raw_activities) else None
        #         hotel_name = (raw_hotel.get("name") if isinstance(raw_hotel, dict) else raw_hotel) or "Hotel TBD"
        #         activity_list = list(raw_day_activities) if isinstance(raw_day_activities, list) else ["Activities TBD"]
        #         flight_info = ""
        #         for f in flights:
        #             if f.get("departure_date") != "N/A" and str(f.get("departure_date", ""))[:10] == date_str:
        #                 flight_info = flight_info + "Flight from " + f.get("origin", "") + " to " + f.get("destination", "") + " on " + str(f.get("departure_date", ""))
        #                 daily_budget += f.get("cost", 0)
        #         flight_info = flight_info or "No flight today"
        #         days.append({
        #             "date": date_str,
        #             "day_number": i + 1,
        #             "activities": activity_list,
        #             "hotel": hotel_name,
        #             "other": flight_info,
        #             "daily_budget": daily_budget,
        #         })
        # else:
        #     days = [{
        #         "date": dep_date or "N/A",
        #         "day_number": 1,
        #         "activities": ["Activities TBD"],
        #         "hotel": "Hotel TBD",
        #         "other": "",
        #         "daily_budget": total_budget,
        #     }]
        # return {"total_budget": total_budget, "flights": flights, "days": days}


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
        "extra_info": data.get("extra_info", "") or "",
    }
    TRIPS.append(trip_data)

    # Get the recommended itinerary from the build_trip_plan function using the trip_data
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


@app.route("/api/additional-info", methods=["POST"])
def api_additional_info():
    """Accept additional info; updates plan via controller and returns the new plan for the GUI."""
    data = request.get_json(force=True, silent=True) or {}
    info = (data.get("info") or "").strip()
    plan = handle_additional_info(info)
    if plan is not None:
        return jsonify({"success": True, "plan": plan})
    if not info:
        return jsonify({"success": True})
    return jsonify({
        "success": False,
        "message": "No plan exists yet. Create a trip first before submitting additional info.",
    }), 400


def main():
    print(f"Starting vacation planning server at http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
