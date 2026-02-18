"""
Overarching ReAct Travel Orchestrator.

Coordinates sub-agents:
- flights_bot
- hotels_bot

Decides which to call, can re-call them, and submits final travel plan.
"""

import json
import os
from typing import Any

from openai import OpenAI

from .flights_bot import run_agent as run_flights_agent
from .hotels_bot import run_agent as run_hotels_agent


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set")

_client = OpenAI(api_key=OPENAI_API_KEY)


# -----------------------------
# TOOL DEFINITIONS
# -----------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_flights_agent",
            "description": "Call the flights sub-agent to search and select optimal flights.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_code": {"type": "string"},
                    "destination": {"type": "string"},
                    "departure_date": {"type": "string"},
                    "return_date": {"type": "string"},
                    "budget_max": {"type": "number"},
                    "prefer_red_eyes": {"type": "boolean"},
                    "extra_info": {"type": "string"},
                },
                "required": ["origin_code", "destination", "departure_date", "return_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_hotels_agent",
            "description": "Call the hotels sub-agent to search and select optimal hotel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                    "budget_max": {"type": "number"},
                    "extra_info": {"type": "string"},
                },
                "required": ["destination", "check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_final_plan",
            "description": "Call this once when the full travel plan is finalized.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flights": {"type": "array"},
                    "hotel": {"type": "object"},
                    "total_estimated_cost": {"type": "number"},
                },
                "required": ["total_estimated_cost"],
            },
        },
    },
]


# -----------------------------
# TOOL RUNNER
# -----------------------------
def _run_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "run_flights_agent":
        flights = run_flights_agent(
            origin_code=arguments["origin_code"],
            destination=arguments["destination"],
            departure_date=arguments["departure_date"],
            return_date=arguments["return_date"],
            budget_max=arguments.get("budget_max", 999999),
            prefer_red_eyes=arguments.get("prefer_red_eyes", False),
            extra_info=arguments.get("extra_info", ""),
        )
        return json.dumps({"flights": flights}, default=str)

    if name == "run_hotels_agent":
        hotel = run_hotels_agent(
            destination=arguments["destination"],
            check_in=arguments["check_in"],
            check_out=arguments["check_out"],
            budget_max=arguments.get("budget_max", 999999),
            extra_info=arguments.get("extra_info", ""),
        )
        return json.dumps({"hotel": hotel}, default=str)

    if name == "submit_final_plan":
        return json.dumps({"status": "complete", **arguments}, default=str)

    return json.dumps({"error": f"Unknown tool: {name}"})


# -----------------------------
# MAIN ORCHESTRATOR
# -----------------------------
def run_orchestrator(
    user_context: str,
    total_budget: float,
    strategy: str = "cheapest_overall",
    model: str = "gpt-4o",
    max_turns: int = 20,
):
    """
    strategy options:
    - cheapest_overall
    - splurge_flight
    - splurge_hotel
    - best_quality
    """

    system_prompt = f"""
You are a senior travel planning agent.

Total budget: {total_budget}
Optimization strategy: {strategy}

Strategies:
- cheapest_overall → minimize total cost
- splurge_flight → allocate ~70% budget to flights
- splurge_hotel → allocate ~60% budget to hotel
- best_quality → maximize quality while staying within total budget

You must:
1. Allocate budget based on strategy.
2. Call sub-agents.
3. If total exceeds budget, rebalance and retry.
4. When satisfied, call submit_final_plan exactly once.
"""

    # Budget allocation logic
    if strategy == "splurge_flight":
        flight_budget = total_budget * 0.7
        hotel_budget = total_budget * 0.3
    elif strategy == "splurge_hotel":
        flight_budget = total_budget * 0.4
        hotel_budget = total_budget * 0.6
    else:
        flight_budget = total_budget
        hotel_budget = total_budget

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_context},
    ]

    current_total = 0
    flights_result = []
    hotel_result = None

    for _ in range(max_turns):
        response = _client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")

                # Inject allocated budgets
                if name == "run_flights_agent":
                    args["budget_max"] = flight_budget

                if name == "run_hotels_agent":
                    args["budget_max"] = hotel_budget

                result = _run_tool(name, args)

                parsed = json.loads(result)

                if name == "run_flights_agent":
                    flights_result = parsed.get("flights", [])
                if name == "run_hotels_agent":
                    hotel_result = parsed.get("hotel")

                # Compute running total
                current_total = 0
                if flights_result:
                    current_total += sum(f["cost"] for f in flights_result)
                if hotel_result:
                    current_total += hotel_result.get("cost", 0)

                # Rebalance if needed
                if current_total > total_budget:
                    # Tighten most expensive component
                    if strategy == "splurge_flight":
                        flight_budget *= 0.9
                    elif strategy == "splurge_hotel":
                        hotel_budget *= 0.9
                    else:
                        flight_budget *= 0.9
                        hotel_budget *= 0.9

                if name == "submit_final_plan":
                    return parsed

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        else:
            break

    return {
        "status": "complete",
        "flights": flights_result,
        "hotel": hotel_result,
        "total_estimated_cost": current_total,
    }
