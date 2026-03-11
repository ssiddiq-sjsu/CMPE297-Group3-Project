"""
Flight search agent using OpenAI Agents SDK and Amadeus.
Reasons over origin, destination, dates, prefer_red_eyes, and budget; acts by querying
Amadeus until it selects optimal flights and returns them via submit_optimal_flights.
Session context is stored in the class for future calls.
"""
import asyncio
import json
import os
from typing import Any, Optional

from agents import Agent, Runner, SQLiteSession, function_tool

from .amadeus_flights import query_flights as amadeus_query_flights

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY is not set")

<<<<<<< HEAD
_client = OpenAI(api_key=OPENAI_API_KEY)
 
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_amadeus_flights",
            "description": "Search Amadeus for flight offers. Use this to get outbound and return options. Call with origin (IATA code, e.g. SFO), destination (city name or IATA, e.g. New York City or JFK), departure_date (YYYY-MM-DD), return_date (YYYY-MM-DD), prefer_red_eyes (bool), and max_budget (float). Returns a list of flight dicts with home_airport, destination, departure_date (with time), arrival_date, cost, airline, duration, flight_number, direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_code": {"type": "string", "description": "Origin airport IATA code (e.g. SFO, JFK)"},
                    "destination": {"type": "string", "description": "Destination city name or IATA code"},
                    "departure_date": {"type": "string", "description": "Departure date YYYY-MM-DD"},
                    "return_date": {"type": "string", "description": "Return date YYYY-MM-DD"},
                    "prefer_red_eyes": {"type": "boolean", "description": "Prefer red-eye (overnight) flights", "default": False},
                    "max_budget": {"type": "number", "description": "Maximum total budget for the search", "default": None},
                },
                "required": ["origin_code", "destination", "departure_date", "return_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_optimal_flights",
            "description": "Call this when you have chosen the optimal flights. Pass a JSON array of flight objects. Each flight must have: home_airport, destination, departure_date (with time, e.g. YYYY-MM-DD HH:MM), arrival_date (with time), cost, airline, duration, flight_number. For round trip you must submit exactly two flights: one outbound, one return.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flights": {
                        "type": "array",
                        "description": "List of chosen flight objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "home_airport": {"type": "string"},
                                "destination": {"type": "string"},
                                "departure_date": {"type": "string"},
                                "arrival_date": {"type": "string"},
                                "cost": {"type": "number"},
                                "airline": {"type": "string"},
                                "duration": {"type": "string"},
                                "flight_number": {"type": "string"},
                            },
                            "required": ["home_airport", "destination", "departure_date", "arrival_date", "cost", "airline", "duration", "flight_number"],
                        },
                    },
                },
                "required": ["flights"],
            },
        },
    },
]
=======

# --- Function tools (Amadeus + submit) ---

@function_tool
def query_amadeus_flights(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: str,
    prefer_red_eyes: bool = False,
    max_budget: float | None = None,
) -> str:
    """Search Amadeus for flight offers. Use this to get outbound and return options.

    Args:
        origin_code: Origin airport IATA code (e.g. SFO, JFK).
        destination: Destination city name or IATA code (e.g. New York City or JFK).
        departure_date: Departure date YYYY-MM-DD.
        return_date: Return date YYYY-MM-DD.
        prefer_red_eyes: Prefer red-eye (overnight) flights.
        max_budget: Maximum total budget for the search (optional).
    """
    result = amadeus_query_flights(
        origin_code=origin_code,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date or None,
        prefer_red_eyes=prefer_red_eyes,
        max_price=max_budget,
    )
    return json.dumps(result, default=str)
>>>>>>> openai_agents_bots


def _make_submit_tool(chosen: list) -> Any:
    """Build a submit_optimal_flights tool that appends the chosen flights to `chosen`."""

    @function_tool
    def submit_optimal_flights(flights_json: str) -> str:
        """Call this when you have chosen the optimal flights. Pass a JSON string that is an array of flight objects.
        Each flight object must have: home_airport, destination, departure_date (with time, e.g. YYYY-MM-DD HH:MM),
        arrival_date (with time), cost, airline, duration, flight_number.
        For round trip submit exactly two flights: first outbound, then return.
        Example: [{"home_airport":"SFO","destination":"JFK","departure_date":"2025-03-01 08:00","arrival_date":"2025-03-01 16:30","cost":250,"airline":"UA","duration":"5h 30m","flight_number":"UA 123"}, ...]

        Args:
            flights_json: JSON array string of chosen flight objects. Each object must have home_airport, destination,
                departure_date, arrival_date, cost, airline, duration, flight_number.
        """
        try:
            flights = json.loads(flights_json)
        except json.JSONDecodeError as e:
            return json.dumps({"status": "error", "message": f"Invalid JSON: {e}"})
        if not isinstance(flights, list):
            return json.dumps({"status": "error", "message": "flights_json must be a JSON array"})
        # Normalize to list of dicts with expected keys (robust to extra keys or string numbers)
        for f in flights:
            if not isinstance(f, dict):
                continue
            chosen.append({
                "home_airport": str(f.get("home_airport", "N/A")),
                "destination": str(f.get("destination", "N/A")),
                "departure_date": str(f.get("departure_date", "N/A")),
                "arrival_date": str(f.get("arrival_date", "N/A")),
                "cost": float(f.get("cost", 0)) if f.get("cost") is not None else 0,
                "airline": str(f.get("airline", "N/A")),
                "duration": str(f.get("duration", "N/A")),
                "flight_number": str(f.get("flight_number", "N/A")),
            })
        return json.dumps({"status": "accepted", "flights": chosen[-len(flights):]}, default=str)

    return submit_optimal_flights


FLIGHT_AGENT_INSTRUCTIONS = """You are a flight search agent. Given the user's origin airport, destination, departure and return dates, preference for red-eye flights, and budget, you must:
1. Call query_amadeus_flights to fetch flight options from Amadeus.
2. Reason over the results (price, duration, red-eye preference, budget).
3. When you have chosen the best outbound and return flights, call submit_optimal_flights exactly once with a list of flight objects. Each object must include: home_airport, destination, departure_date (with time, e.g. YYYY-MM-DD HH:MM), arrival_date (with time), cost, airline, duration, flight_number.
For a round trip, submit exactly two flights: first the outbound, then the return. You must call submit_optimal_flights when done; do not reply with only text."""


def _clear_session_sync(session: SQLiteSession) -> None:
    """Clear session from sync code (session.clear_session is async)."""
    asyncio.run(session.clear_session())


class FlightSearchAgent:
    """
    Stateful flight search agent. Stores an Agents API session so the same
    conversation continues across calls. When search params change, session is cleared.
    """

    def __init__(self, session_id: str = "flight_search", db_path: Optional[str] = None) -> None:
        self._session = SQLiteSession(session_id, db_path) if db_path else SQLiteSession(session_id)
        self._search_params: Optional[dict[str, Any]] = None

    def _current_search_key(
        self,
        origin_code: str,
        destination: str,
        departure_date: str,
        return_date: str,
        budget_max: float,
    ) -> tuple:
        return (
            origin_code.strip(),
            destination.strip(),
            departure_date.strip(),
            (return_date or "").strip(),
            float(budget_max),
        )

    def run(
        self,
        origin_code: str,
        destination: str,
        departure_date: str,
        return_date: str,
        budget_max: float,
        prefer_red_eyes: bool = False,
        extra_info: str = "",
    ) -> list[dict]:
        """
        Run the flight search agent using the stored session. Returns a list of flight dicts,
        each with: home_airport, destination, departure_date (with time), arrival_date, cost,
        airline, duration, flight_number.
        """
        key = self._current_search_key(origin_code, destination, departure_date, return_date, budget_max)
        if self._search_params is None or self._search_params.get("_key") != key:
            _clear_session_sync(self._session)
            self._search_params = {
                "_key": key,
                "origin_code": origin_code,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "budget_max": budget_max,
            }

        chosen: list[dict] = []
        submit_tool = _make_submit_tool(chosen)
        agent = Agent(
            name="Flight Search Agent",
            instructions=FLIGHT_AGENT_INSTRUCTIONS,
            tools=[query_amadeus_flights, submit_tool],
        )

        user_content = (
            f"Search for flights with:\n"
            f"- Origin (home airport): {origin_code}\n"
            f"- Destination: {destination}\n"
            f"- Departure date: {departure_date}\n"
            f"- Return date: {return_date}\n"
            f"- Prefer red-eye flights: {prefer_red_eyes}\n"
            f"- Maximum budget (total): {budget_max}\n"
            f"- Extra information: {extra_info or 'None'}\n\n"
            "Use query_amadeus_flights to get options, then call submit_optimal_flights with your chosen flights."
        )

        Runner.run_sync(agent, user_content, session=self._session)

        return chosen


_default_agent = FlightSearchAgent()


def run_agent(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: str,
    budget_max: float,
    prefer_red_eyes: bool = False,
    extra_info: str = "",
    model: str = "gpt-4o",
    max_turns: int = 15,
) -> list[dict]:
    """
    Run the flight search agent. Returns a list of flight dicts, each with:
    home_airport, destination, departure_date (with time), arrival_date, cost, airline, duration, flight_number.
    """
    return _default_agent.run(
        origin_code=origin_code,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        budget_max=float(budget_max),
        prefer_red_eyes=prefer_red_eyes,
        extra_info=extra_info or "",
    )
