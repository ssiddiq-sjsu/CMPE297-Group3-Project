"""
Controller agent using OpenAI Agents SDK. Orchestrates flight and hotel bots to build
a trip plan. Stores session context; on first call takes instructions and returns a plan;
on subsequent calls uses extra_info and session memory to update the plan.
"""
import asyncio
import json
import os
from datetime import date, timedelta
from typing import Any, Optional

from agents import Agent, Runner, SQLiteSession, function_tool

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY is not set")


def _clear_session_sync(session: SQLiteSession) -> None:
    asyncio.run(session.clear_session())


CONTROLLER_INSTRUCTIONS = """You are a trip planning controller. The user gives you trip instructions (origin, destination, dates, budget, and optional extra_info). You must:
1. Call get_flights with the origin, destination, departure_date, return_date, budget_max, prefer_red_eyes, and extra_info to fetch flight options.
2. Call get_hotels with the destination, check_in (same as departure_date), check_out (same as return_date), budget_max, and extra_info to fetch hotel options.
You must call both get_flights and get_hotels to produce a complete plan. Use the exact parameter values from the user message. On subsequent messages the user may provide extra_info to refine the plan; call both tools again with the same base parameters but the new extra_info."""


def _make_get_flights_tool(controller: "TripControllerAgent") -> Any:
    @function_tool
    def get_flights(
        origin_code: str,
        destination: str,
        departure_date: str,
        return_date: str,
        budget_max: float,
        prefer_red_eyes: bool = False,
        extra_info: str = "",
    ) -> str:
        """Fetch flight options for the trip. Call this with the user's origin, destination, dates, budget, and optional extra_info.

        Args:
            origin_code: Origin airport IATA code (e.g. SFO, JFK).
            destination: Destination city or code.
            departure_date: Departure date YYYY-MM-DD.
            return_date: Return date YYYY-MM-DD.
            budget_max: Maximum total budget for flights.
            prefer_red_eyes: Prefer red-eye flights.
            extra_info: Optional user preferences or refinement notes.
        """
        return controller._fetch_flights(
            origin_code=origin_code,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            budget_max=budget_max,
            prefer_red_eyes=prefer_red_eyes,
            extra_info=extra_info,
        )

    return get_flights


def _make_get_hotels_tool(controller: "TripControllerAgent") -> Any:
    @function_tool
    def get_hotels(
        destination: str,
        check_in: str,
        check_out: str,
        budget_max: float,
        extra_info: str = "",
    ) -> str:
        """Fetch hotel options for the trip. Call this with the user's destination, check-in/check-out dates, budget, and optional extra_info.

        Args:
            destination: Destination city or code.
            check_in: Check-in date YYYY-MM-DD.
            check_out: Check-out date YYYY-MM-DD.
            budget_max: Maximum budget for the stay.
            extra_info: Optional user preferences or refinement notes.
        """
        return controller._fetch_hotels(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            budget_max=budget_max,
            extra_info=extra_info,
        )

    return get_hotels


class TripControllerAgent:
    """
    Controller agent that builds trip plans by calling flights and hotels bots.
    Stores session so subsequent calls can use extra_info to update the plan.
    """

    def __init__(self, session_id: str = "trip_controller", db_path: Optional[str] = None) -> None:
        self._session = SQLiteSession(session_id, db_path) if db_path else SQLiteSession(session_id)
        self._trip_key: Optional[tuple] = None
        self._last_raw_flights: Optional[list[dict]] = None
        self._last_raw_hotels: Optional[list[dict]] = None

    def _trip_key_from_data(self, trip_data: dict) -> tuple:
        return (
            str(trip_data.get("home_airport", "")).strip(),
            str(trip_data.get("destination", "")).strip(),
            str(trip_data.get("departure_date", "")).strip(),
            str(trip_data.get("return_date", "")).strip(),
            float(trip_data.get("budget", 0)),
        )

    def _fetch_flights(
        self,
        origin_code: str,
        destination: str,
        departure_date: str,
        return_date: str,
        budget_max: float,
        prefer_red_eyes: bool = False,
        extra_info: str = "",
    ) -> str:
        from .flights_bot import run_agent as run_flights_agent
        agent_flights = run_flights_agent(
            origin_code=origin_code,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            budget_max=float(budget_max),
            prefer_red_eyes=prefer_red_eyes,
            extra_info=extra_info or "",
        )
        if not agent_flights:
            self._last_raw_flights = None
            return json.dumps({"flights": [], "message": "No flights found."})
        raw = []
        for f in agent_flights:
            raw.append({
                "description": f"{f.get('airline', 'N/A')} {f.get('flight_number', 'N/A')}: {f.get('home_airport', 'N/A')} → {f.get('destination', 'N/A')} ({f.get('duration', 'N/A')})",
                "origin": f.get("home_airport", "N/A"),
                "destination": f.get("destination", "N/A"),
                "departure_date": f.get("departure_date", "N/A"),
                "arrival_date": f.get("arrival_date", "N/A"),
                "cost": float(f.get("cost", 0)),
                "airline": f.get("airline", "N/A"),
                "duration": f.get("duration", "N/A"),
                "flight_number": f.get("flight_number", "N/A"),
            })
        self._last_raw_flights = raw
        return json.dumps({"flights": raw, "count": len(raw)}, default=str)

    def _fetch_hotels(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        budget_max: float,
        extra_info: str = "",
    ) -> str:
        from .hotels_bot import run_agent as run_hotel_agent
        hotels = run_hotel_agent(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            budget_max=float(budget_max),
            extra_info=extra_info or "",
        )
        if not hotels:
            self._last_raw_hotels = None
            return json.dumps({"hotels": [], "message": "No hotels found."})
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
        self._last_raw_hotels = raw
        return json.dumps({"hotels": raw, "count": len(raw)}, default=str)

    def _build_plan_from_raw(
        self,
        trip_data: dict,
        raw_flights: Optional[list[dict]],
        raw_hotels: Optional[list[dict]],
        raw_activities: Optional[list],
    ) -> dict:
        """Build the same plan structure as server.build_trip_plan for the GUI API."""
        origin = trip_data.get("home_airport", "N/A")
        destination = trip_data.get("destination", "N/A")
        dep_date = trip_data.get("departure_date", "")
        ret_date = trip_data.get("return_date", "")
        total_budget = float(trip_data.get("budget", 0))
        activity_types = trip_data.get("activity_types") or []

        flights = []
        if raw_flights:
            for f in raw_flights:
                flights.append({
                    "description": f.get("description", "Flight"),
                    "origin": f.get("origin", "N/A"),
                    "destination": f.get("destination", "N/A"),
                    "departure_date": f.get("departure_date", "N/A"),
                    "arrival_date": f.get("arrival_date", "N/A"),
                    "cost": float(f.get("cost", 0)),
                })
        else:
            flights = [
                {"description": f"Outbound: {origin} → {destination} ({dep_date}) — placeholder", "origin": origin, "destination": destination, "departure_date": dep_date, "arrival_date": dep_date, "cost": 0},
                {"description": f"Return: {destination} → {origin} ({ret_date}) — placeholder", "origin": destination, "destination": origin, "departure_date": ret_date, "arrival_date": ret_date, "cost": 0},
            ]

        days = []
        try:
            dep_d = date.fromisoformat(dep_date) if dep_date else None
            ret_d = date.fromisoformat(ret_date) if ret_date else None
        except ValueError:
            dep_d = ret_d = None
        if dep_d and ret_d and dep_d < ret_d:
            day_count = (ret_d - dep_d).days + 1
            for i in range(day_count):
                daily_budget = 0
                d = dep_d + timedelta(days=i)
                date_str = d.isoformat()
                raw_hotel = raw_hotels[min(i, len(raw_hotels) - 1)] if raw_hotels else None
                raw_day_activities = raw_activities[i] if raw_activities and i < len(raw_activities) else None
                hotel_name = (raw_hotel.get("name") if isinstance(raw_hotel, dict) else raw_hotel) if raw_hotel else "Hotel TBD"
                activity_list = list(raw_day_activities) if isinstance(raw_day_activities, list) else ["Activities TBD"]
                flight_info = ""
                for f in flights:
                    if f.get("departure_date") != "N/A" and str(f.get("departure_date", ""))[:10] == date_str:
                        flight_info = flight_info + "Flight from " + f.get("origin", "") + " to " + f.get("destination", "") + " on " + str(f.get("departure_date", ""))
                        daily_budget += f.get("cost", 0)
                flight_info = flight_info if flight_info else "No flight today"
                days.append({
                    "date": date_str,
                    "day_number": i + 1,
                    "activities": activity_list,
                    "hotel": hotel_name,
                    "other": flight_info,
                    "daily_budget": daily_budget,
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

    def run(self, current_plan: dict, trip_data: dict) -> dict:
        """
        Run the controller agent. Uses session for context. Calls flights and hotels bots
        and returns a new plan for the GUI API.
        Args:
            current_plan: Previous plan (empty dict or None on first call).
            trip_data: home_airport, destination, departure_date, return_date, budget, prefer_red_eyes, activity_types, extra_info (optional).
        Returns:
            Plan dict: total_budget, flights, days (same shape as build_trip_plan).
        """
        key = self._trip_key_from_data(trip_data)
        if self._trip_key != key:
            _clear_session_sync(self._session)
            self._trip_key = key
        self._last_raw_flights = None
        self._last_raw_hotels = None

        origin = trip_data.get("home_airport", "")
        destination = trip_data.get("destination", "")
        dep_date = trip_data.get("departure_date", "")
        ret_date = trip_data.get("return_date", "")
        budget = float(trip_data.get("budget", 0))
        prefer_red_eyes = bool(trip_data.get("prefer_red_eyes", False))
        extra_info = str(trip_data.get("extra_info", "") or "")

        agent = Agent(
            name="Trip Controller",
            instructions=CONTROLLER_INSTRUCTIONS,
            tools=[
                _make_get_flights_tool(self),
                _make_get_hotels_tool(self),
            ],
        )

        plan_summary = json.dumps(current_plan, default=str)[:500] if current_plan else "No plan yet."
        user_content = (
            f"Current plan (for context): {plan_summary}\n\n"
            f"Trip instructions:\n"
            f"- Origin (home airport): {origin}\n"
            f"- Destination: {destination}\n"
            f"- Departure date: {dep_date}\n"
            f"- Return date: {ret_date}\n"
            f"- Budget: {budget}\n"
            f"- Prefer red-eye flights: {prefer_red_eyes}\n"
            f"- Extra info / preferences: {extra_info or 'None'}\n\n"
            "Call get_flights and get_hotels with these parameters to build or update the plan. Use the extra_info when calling both tools."
        )

        Runner.run_sync(agent, user_content, session=self._session)

        raw_activities = None  # TODO: activity types when search_activities is implemented
        return self._build_plan_from_raw(
            trip_data,
            self._last_raw_flights,
            self._last_raw_hotels,
            raw_activities,
        )


_default_controller = TripControllerAgent()


def run_controller(current_plan: dict, trip_data: dict) -> dict:
    """Run the trip controller agent; returns a plan dict for the GUI API."""
    return _default_controller.run(current_plan or {}, trip_data)
