"""
ReAct flight search agent using OpenAI (ChatGPT) and Amadeus.
Reasons over origin, destination, dates, prefer_red_eyes, and budget; acts by querying
Amadeus until it selects optimal flights and returns them via submit_optimal_flights.
"""
import json
import os
from typing import Any

from openai import OpenAI

from .amadeus import query_flights as amadeus_query_flights

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set")

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


def _run_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "query_amadeus_flights":
        print("running query_amadeus_flights with arguments: ", arguments)
        result = amadeus_query_flights(
            origin_code=str(arguments.get("origin_code", "")),
            destination=str(arguments.get("destination", "")),
            departure_date=str(arguments.get("departure_date", "")),
            return_date=arguments.get("return_date") or None,
            prefer_red_eyes=bool(arguments.get("prefer_red_eyes", False)),
            max_price=arguments.get("max_budget"),
        )
        print("amadeus_query_flights result: ", result)
        return json.dumps(result, default=str)
    if name == "submit_optimal_flights":
        print("running submit_optimal_flights with arguments: ", arguments)
        return json.dumps({"status": "accepted", "flights": arguments.get("flights", [])}, default=str)
    return json.dumps({"error": f"Unknown tool: {name}"})


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
    Run the ReAct flight search agent. Returns a list of flight dicts, each with:
    home_airport, destination, departure_date (with time), arrival_date, cost, airline, duration, flight_number.
    """
    system = """You are a flight search agent. Given the user's origin airport, destination, departure and return dates, preference for red-eye flights, and budget, you must:
1. Call query_amadeus_flights to fetch flight options from Amadeus.
2. Reason over the results (price, duration, red-eye preference, budget).
3. When you have chosen the best outbound and return flights, call submit_optimal_flights exactly once with a list of flight objects. Each object must include: home_airport, destination, departure_date (with time, e.g. YYYY-MM-DD HH:MM), arrival_date (with time), cost, airline, duration, flight_number.
For a round trip, submit exactly two flights: first the outbound, then the return. You must call submit_optimal_flights when done; do not reply with only text."""
# realistically I want to add some examples in the context and make this properly react since this isn't lol. but this also works for now

    user_content = (
        f"Search for flights with:\n"
        f"- Origin (home airport): {origin_code}\n"
        f"- Destination: {destination}\n"
        f"- Departure date: {departure_date}\n"
        f"- Return date: {return_date}\n"
        f"- Prefer red-eye flights: {prefer_red_eyes}\n"
        f"- Maximum budget (total): {budget_max}\n"
        f"Use query_amadeus_flights to get options, then call submit_optimal_flights with your chosen flights."
        f"- Extra information: {extra_info}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    for _ in range(max_turns):
        response = _client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        msg = choice.message
        if msg.content and not (msg.tool_calls):
            break
        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _run_tool(name, args)
                if name == "submit_optimal_flights":
                    try:
                        data = json.loads(result)
                        print("messages: ", messages)
                        return data.get("flights", [])
                    except (json.JSONDecodeError, KeyError):
                        pass
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            continue
        break
    
    print("messages: ", messages)
    return []
