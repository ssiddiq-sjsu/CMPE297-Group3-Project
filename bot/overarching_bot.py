"""
Overarching ReAct Travel Orchestrator.

Coordinates sub-agents:
- flights_bot
- hotels_bot

Decides which to call, can re-call them, and submits final travel plan.
"""

import json
from typing import Dict, Any, List
from openai import OpenAI

from .flights_bot import run_agent as run_flights_agent
from .hotels_bot import run_agent as run_hotels_agent

client = OpenAI()


# ==========================================================
# DETERMINISTIC OPTIMIZER
# ==========================================================

def optimize_trip(
    flights: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    total_budget: float,
    strategy: str,
) -> Dict[str, Any]:

    flights_sorted = sorted(flights, key=lambda x: x["cost"])
    hotels_sorted = sorted(hotels, key=lambda x: x["cost"])

    if not flights_sorted or not hotels_sorted:
        return {"error": "Missing flight or hotel results."}

    # Always select cheapest flight combo (2 legs)
    selected_flights = flights_sorted[:2]
    flight_cost = sum(f["cost"] for f in selected_flights)

    # Always select cheapest hotel
    selected_hotel = hotels_sorted[0]
    hotel_cost = selected_hotel["cost"]

    total_cost = flight_cost + hotel_cost

    if total_cost <= total_budget:
        return {
            "status": "complete",
            "strategy": strategy,
            "flights": selected_flights,
            "hotel": selected_hotel,
            "total_cost": total_cost,
            "remaining_budget": total_budget - total_cost,
        }

    # Rebalancing logic
    flight_ratio = 0.7 if strategy == "splurge_flight" else 0.4
    if strategy == "cheapest_overall":
        flight_ratio = 1.0

    hotel_ratio = 1 - flight_ratio

    for _ in range(10):

        flight_cap = total_budget * flight_ratio
        hotel_cap = total_budget * hotel_ratio

        valid_flights = [f for f in flights_sorted if f["cost"] <= flight_cap]
        valid_hotels = [h for h in hotels_sorted if h["cost"] <= hotel_cap]

        if not valid_flights or not valid_hotels:
            flight_ratio = min(0.9, flight_ratio + 0.05)
            hotel_ratio = 1 - flight_ratio
            continue

        selected_flights = valid_flights[:2]
        selected_hotel = valid_hotels[0]

        total_cost = sum(f["cost"] for f in selected_flights) + selected_hotel["cost"]

        if total_cost <= total_budget:
            return {
                "status": "complete",
                "strategy": strategy,
                "flights": selected_flights,
                "hotel": selected_hotel,
                "total_cost": total_cost,
                "remaining_budget": total_budget - total_cost,
                "allocation_used": {
                    "flight_ratio": round(flight_ratio, 2),
                    "hotel_ratio": round(hotel_ratio, 2),
                },
            }

        flight_ratio = max(0.1, flight_ratio - 0.05)
        hotel_ratio = 1 - flight_ratio

    return {"error": "No valid combination within budget."}


# ==========================================================
# TOOL DEFINITIONS
# ==========================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Search round trip flights",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "departure_date": {"type": "string"},
                    "return_date": {"type": "string"},
                },
                "required": ["origin", "destination", "departure_date", "return_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search hotels",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                },
                "required": ["destination", "check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_trip",
            "description": "Optimize flight and hotel within total budget",
            "parameters": {
                "type": "object",
                "properties": {
                    "flights": {"type": "array"},
                    "hotels": {"type": "array"},
                    "total_budget": {"type": "number"},
                    "strategy": {
                        "type": "string",
                        "enum": ["cheapest_overall", "splurge_flight", "splurge_hotel"],
                    },
                },
                "required": ["flights", "hotels", "total_budget", "strategy"],
            },
        },
    },
]


# ==========================================================
# REACT STYLE LOOP
# ==========================================================

def run_overarching_bot(user_input: str) -> str:

    messages = [
        {
            "role": "system",
            "content": """
You are a travel orchestrator.
You must:
1. Call search_flights
2. Call search_hotels
3. Call optimize_trip
Use cheapest_overall unless user specifies splurge preference.
Stop once optimize_trip returns success.
""",
        },
        {"role": "user", "content": user_input},
    ]

    while True:

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            if name == "search_flights":
                result = run_flights_agent(
                    origin_code=args["origin"],
                    destination=args["destination"],
                    departure_date=args["departure_date"],
                    return_date=args["return_date"],
                )

            elif name == "search_hotels":
                result = run_hotels_agent(
                    destination=args["destination"],
                    check_in=args["check_in"],
                    check_out=args["check_out"],
                )

            elif name == "optimize_trip":
                result = optimize_trip(
                    flights=args["flights"],
                    hotels=args["hotels"],
                    total_budget=args["total_budget"],
                    strategy=args["strategy"],
                )

            messages.append(message)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

        else:
            return message.content