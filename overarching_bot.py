"""
Overarching ReAct Travel Orchestrator.

Coordinates sub-agents:
- flights_bot
- hotels_bot

Features:
- Intelligent budget optimization that checks feasibility before adjusting
- Handles edge cases where cheaper options may not exist
- Automatic re-running of agents when needed
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from openai import OpenAI

from flights_bot import run_agent as run_flights_agent
from hotels_bot import run_agent as run_hotels_agent

client = OpenAI()


# ==========================================================
# TYPES AND ENUMS
# ==========================================================

class Strategy(str, Enum):
    CHEAPEST_OVERALL = "cheapest_overall"
    SPLURGE_FLIGHT = "splurge_flight"
    SPLURGE_HOTEL = "splurge_hotel"

class OptimizationStatus(str, Enum):
    COMPLETE = "complete"
    NEED_MORE_OPTIONS = "need_more_options"      # Need to find ANY options (increase budget)
    NEED_CHEAPER_OPTIONS = "need_cheaper_options" # Need CHEAPER options (decrease budget)
    ERROR = "error"

# Type alias for flexible item dictionaries
TripItem = Dict[str, Any]

@dataclass
class OptimizationResult:
    """Result of trip optimization with all possible fields"""
    status: OptimizationStatus
    message: Optional[str] = None
    flights: Optional[List[TripItem]] = None
    hotel: Optional[TripItem] = None
    total_cost: Optional[float] = None
    remaining_budget: Optional[float] = None
    flight_budget: Optional[float] = None
    hotel_budget: Optional[float] = None
    flight_ratio: Optional[float] = None
    hotel_ratio: Optional[float] = None
    component_to_adjust: Optional[str] = None  # Which component needs adjustment
    keep_flights: Optional[List[TripItem]] = None  # Flights to preserve if adjusting hotels
    keep_hotel: Optional[TripItem] = None  # Hotel to preserve if adjusting flights
    error: Optional[str] = None

@dataclass
class BudgetConstraints:
    flight_budget: Optional[float] = None
    hotel_budget: Optional[float] = None
    component_to_adjust: Optional[str] = None
    keep_flights: Optional[List[TripItem]] = None
    keep_hotel: Optional[TripItem] = None
    
    def clear(self):
        self.flight_budget = None
        self.hotel_budget = None
        self.component_to_adjust = None
        self.keep_flights = None
        self.keep_hotel = None


# ==========================================================
# INTELLIGENT OPTIMIZER
# ==========================================================

def optimize_trip(
    flights: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    total_budget: float,
    strategy: Strategy,
) -> OptimizationResult:
    """
    Optimize flight and hotel selection within budget.
    Uses intelligent decision-making to avoid infinite loops.
    """
    
    # Sort by cost for consistent selection and feasibility checking
    flights_sorted = sorted(flights, key=lambda x: x["cost"])
    hotels_sorted = sorted(hotels, key=lambda x: x["cost"])
    
    if not flights_sorted or not hotels_sorted:
        missing = []
        if not flights_sorted:
            missing.append("flights")
        if not hotels_sorted:
            missing.append("hotels")
        return OptimizationResult(
            status=OptimizationStatus.ERROR,
            error=f"Missing {', '.join(missing)} results"
        )
    
    # Get initial allocation based on strategy
    allocation = _get_initial_allocation(strategy)
    flight_ratio, hotel_ratio = allocation["flight"], allocation["hotel"]
    
    for iteration in range(10):  # Max 10 attempts
        flight_budget = total_budget * flight_ratio
        hotel_budget = total_budget * hotel_ratio
        
        # Find options within budget
        valid_flights = [f for f in flights_sorted if f["cost"] <= flight_budget]
        valid_hotels = [h for h in hotels_sorted if h["cost"] <= hotel_budget]
        
        # CASE 1: No flights found - need to increase flight budget
        if not valid_flights:
            new_flight_ratio = min(0.9, flight_ratio + 0.05)
            return OptimizationResult(
                status=OptimizationStatus.NEED_MORE_OPTIONS,
                message=f"No flights found within ${flight_budget:.2f}. Need more flight budget.",
                flight_budget=total_budget * new_flight_ratio,
                hotel_budget=hotel_budget,
                flight_ratio=new_flight_ratio,
                hotel_ratio=1 - new_flight_ratio,
                component_to_adjust="flights"
            )
        
        # CASE 2: No hotels found - need to increase hotel budget
        if not valid_hotels:
            new_hotel_ratio = min(0.9, hotel_ratio + 0.05)
            return OptimizationResult(
                status=OptimizationStatus.NEED_MORE_OPTIONS,
                message=f"No hotels found within ${hotel_budget:.2f}. Need more hotel budget.",
                flight_budget=flight_budget,
                hotel_budget=total_budget * new_hotel_ratio,
                flight_ratio=1 - new_hotel_ratio,
                hotel_ratio=new_hotel_ratio,
                component_to_adjust="hotels"
            )
        
        # Select cheapest options within current budgets
        selected_flights = valid_flights[:2]  # Round trip
        selected_hotel = valid_hotels[0]
        total_cost = sum(f["cost"] for f in selected_flights) + selected_hotel["cost"]
        
        # CASE 3: Within budget - success!
        if total_cost <= total_budget:
            print("="*50)
            print("FOUND SOLUTION:")
            print(f"Flights: {selected_flights}")
            print(f"Hotel: {selected_hotel}")
            print(f"Total: {total_cost}")
            print("="*50)
            
            return OptimizationResult(
                status=OptimizationStatus.COMPLETE,
                flights=selected_flights,
                hotel=selected_hotel,
                total_cost=total_cost,
                remaining_budget=total_budget - total_cost,
                message="Found optimized solution",
                flight_budget=flight_budget,
                hotel_budget=hotel_budget,
                flight_ratio=round(flight_ratio, 2),
                hotel_ratio=round(hotel_ratio, 2)
            )
        
        # CASE 4: Over budget - need intelligent adjustment
        # Calculate current costs
        flight_cost = sum(f["cost"] for f in selected_flights)
        hotel_cost = selected_hotel["cost"]
        
        # Check if cheaper options exist in the FULL dataset
        # Find the index of current selection in sorted list
        flight_index = next(i for i, f in enumerate(flights_sorted) 
                           if f["cost"] >= flight_cost)
        hotel_index = next(i for i, h in enumerate(hotels_sorted) 
                          if h["cost"] >= hotel_cost)
        
        # Cheaper options exist if current index is not the first/cheapest
        cheaper_flights_exist = flight_index > 1  # At least one cheaper flight exists (need 2 for round trip)
        cheaper_hotels_exist = hotel_index > 0    # At least one cheaper hotel exists
        
        # INTELLIGENT DECISION LOGIC
        if flight_cost > hotel_cost:
            # Flights are the expensive component
            if cheaper_flights_exist:
                # We CAN make flights cheaper - reduce flight allocation
                new_flight_ratio = max(0.1, flight_ratio - 0.05)
                return OptimizationResult(
                    status=OptimizationStatus.NEED_CHEAPER_OPTIONS,
                    message=f"Total ${total_cost:.2f} exceeds budget. Reducing flight budget to find cheaper flights.",
                    flight_budget=total_budget * new_flight_ratio,
                    hotel_budget=total_budget * (1 - new_flight_ratio),
                    flight_ratio=new_flight_ratio,
                    hotel_ratio=1 - new_flight_ratio,
                    component_to_adjust="flights",
                    keep_hotel=selected_hotel
                )
            else:
                # No cheaper flights exist - we MUST reduce hotels instead
                new_hotel_ratio = max(0.1, hotel_ratio - 0.05)
                return OptimizationResult(
                    status=OptimizationStatus.NEED_CHEAPER_OPTIONS,
                    message=f"Total ${total_cost:.2f} exceeds budget and no cheaper flights exist. Reducing hotel budget to find cheaper hotels.",
                    flight_budget=total_budget * (1 - new_hotel_ratio),
                    hotel_budget=total_budget * new_hotel_ratio,
                    flight_ratio=1 - new_hotel_ratio,
                    hotel_ratio=new_hotel_ratio,
                    component_to_adjust="hotels",
                    keep_flights=selected_flights
                )
        else:
            # Hotels are the expensive component (or equal)
            if cheaper_hotels_exist:
                # We CAN make hotels cheaper - reduce hotel allocation
                new_hotel_ratio = max(0.1, hotel_ratio - 0.05)
                return OptimizationResult(
                    status=OptimizationStatus.NEED_CHEAPER_OPTIONS,
                    message=f"Total ${total_cost:.2f} exceeds budget. Reducing hotel budget to find cheaper hotels.",
                    flight_budget=total_budget * (1 - new_hotel_ratio),
                    hotel_budget=total_budget * new_hotel_ratio,
                    flight_ratio=1 - new_hotel_ratio,
                    hotel_ratio=new_hotel_ratio,
                    component_to_adjust="hotels",
                    keep_flights=selected_flights
                )
            else:
                # No cheaper hotels exist - we MUST reduce flights instead
                new_flight_ratio = max(0.1, flight_ratio - 0.05)
                return OptimizationResult(
                    status=OptimizationStatus.NEED_CHEAPER_OPTIONS,
                    message=f"Total ${total_cost:.2f} exceeds budget and no cheaper hotels exist. Reducing flight budget to find cheaper flights.",
                    flight_budget=total_budget * new_flight_ratio,
                    hotel_budget=total_budget * (1 - new_flight_ratio),
                    flight_ratio=new_flight_ratio,
                    hotel_ratio=1 - new_flight_ratio,
                    component_to_adjust="flights",
                    keep_hotel=selected_hotel
                )
    
    # If we exhaust all iterations
    return OptimizationResult(
        status=OptimizationStatus.ERROR,
        error="No valid combination within budget after multiple attempts"
    )

def _get_initial_allocation(strategy: Strategy) -> Dict[str, float]:
    """Get initial budget allocation based on strategy."""
    allocations = {
        Strategy.CHEAPEST_OVERALL: {"flight": 0.5, "hotel": 0.5},
        Strategy.SPLURGE_FLIGHT: {"flight": 0.7, "hotel": 0.3},
        Strategy.SPLURGE_HOTEL: {"flight": 0.3, "hotel": 0.7},
    }
    return allocations.get(strategy, allocations[Strategy.CHEAPEST_OVERALL])


# ==========================================================
# TOOL DEFINITIONS - FIXED WITH PROPER ARRAY SCHEMAS
# ==========================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Search for round-trip flights",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Origin airport code"},
                    "destination": {"type": "string", "description": "Destination airport code"},
                    "departure_date": {"type": "string", "description": "Departure date (YYYY-MM-DD)"},
                    "return_date": {"type": "string", "description": "Return date (YYYY-MM-DD)"},
                    "max_budget": {"type": "number", "description": "Maximum budget per flight", "optional": True}
                },
                "required": ["origin", "destination", "departure_date", "return_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search for hotels",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "Destination city or area"},
                    "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                    "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"},
                    "max_budget": {"type": "number", "description": "Maximum budget per night", "optional": True}
                },
                "required": ["destination", "check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_trip",
            "description": "Optimize flight and hotel selection within total budget",
            "parameters": {
                "type": "object",
                "properties": {
                    "flights": {
                        "type": "array",
                        "description": "List of available flights",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cost": {"type": "number"},
                                "airline": {"type": "string"},
                                "flight_number": {"type": "string"},
                                "home_airport": {"type": "string"},
                                "destination": {"type": "string"},
                                "departure_date": {"type": "string"},
                                "arrival_date": {"type": "string"},
                                "duration": {"type": "string"}
                            }
                        }
                    },
                    "hotels": {
                        "type": "array",
                        "description": "List of available hotels",
                        "items": {
                            "type": "object",
                            "properties": {
                                "cost": {"type": "number"},
                                "name": {"type": "string"},
                                "hotelId": {"type": "string"},
                                "rating": {"type": "string"},
                                "currency": {"type": "string"},
                                "offerId": {"type": "string"}
                            }
                        }
                    },
                    "total_budget": {"type": "number", "description": "Total trip budget"},
                    "strategy": {
                        "type": "string",
                        "enum": [s.value for s in Strategy],
                        "description": "Optimization strategy"
                    }
                },
                "required": ["flights", "hotels", "total_budget", "strategy"],
            },
        },
    },
]


# ==========================================================
# REACT LOOP WITH INTELLIGENT STATE MANAGEMENT
# ==========================================================

def run_overarching_bot(user_input: str) -> str:
    """
    Main orchestrator loop with intelligent budget optimization.
    """
    
    messages = [
        {
            "role": "system",
            "content": f"""
You are a travel orchestrator coordinating flight and hotel searches.
Available strategies: {', '.join([s.value for s in Strategy])}

Follow this process:
1. Extract travel details from user (origin, destination, dates, budget, preference)
2. Call search_flights to find available flights
3. Call search_hotels to find available hotels
4. Call optimize_trip with the results
5. If optimize_trip returns need_more_options, re-run the specified agent with increased budget
6. If optimize_trip returns need_cheaper_options, re-run the specified agent with decreased budget, preserving the other component's selection
7. Stop when optimize_trip returns complete

Default to {Strategy.CHEAPEST_OVERALL.value} strategy unless user specifies otherwise.
""",
        },
        {"role": "user", "content": user_input},
    ]
    
    constraints = BudgetConstraints()
    
    while True:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            
            message = response.choices[0].message
            
            # Add the assistant's message to the history
            messages.append(message)
            
            # If there are no tool calls, return the content
            if not message.tool_calls:
                return message.content or "No response generated"
            
            # Process each tool call
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                print(f"\n\n🔧 Tool called: {name}")
                print(f"Arguments: {json.dumps(args, indent=2)}")
                
                # Execute the appropriate tool with constraints
                result = _execute_tool(name, args, constraints)
                
                print(f"Result: {json.dumps(result, default=str, indent=2)[:500]}...")
                
                # Add the tool response message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
                
                # Check if we're done (only check on optimize_trip calls)
                if name == "optimize_trip" and result.get("status") == OptimizationStatus.COMPLETE.value:
                    # Return both formatted response AND the data
                    formatted = _format_final_response(result)
                    return json.dumps({
                        "formatted": formatted,
                        "data": {
                            "flights": result.get("flights", []),
                            "hotel": result.get("hotel", {}),
                            "total_cost": result.get("total_cost", 0),
                            "remaining_budget": result.get("remaining_budget", 0),
                            "flight_ratio": result.get("flight_ratio"),
                            "hotel_ratio": result.get("hotel_ratio")
                        }
                    }, default=str)
            
        except Exception as e:
            return f"Error in orchestration: {str(e)}"

def _execute_tool(
    name: str, 
    args: Dict[str, Any], 
    constraints: BudgetConstraints
) -> Dict[str, Any]:
    """Execute the appropriate tool with current constraints."""
    
    if name == "search_flights":
        # Apply flight budget constraint if available
        if constraints.flight_budget:
            args["max_budget"] = constraints.flight_budget
        
        result = run_flights_agent(
            origin_code=args["origin"],
            destination=args["destination"],
            departure_date=args["departure_date"],
            return_date=args["return_date"],
            max_budget=args.get("max_budget"),
        )
        
        # Clear used constraints
        constraints.clear()
        return result
    
    elif name == "search_hotels":
        # Apply hotel budget constraint if available
        if constraints.hotel_budget:
            args["max_budget"] = constraints.hotel_budget
        
        result = run_hotels_agent(
            destination=args["destination"],
            check_in=args["check_in"],
            check_out=args["check_out"],
            max_budget=args.get("max_budget"),
        )
        
        # Clear used constraints
        constraints.clear()
        return result
    
    elif name == "optimize_trip":
        strategy = Strategy(args.get("strategy", Strategy.CHEAPEST_OVERALL.value))
        
        # If we have preserved items from previous iteration, add them back
        if constraints.keep_flights:
            args["flights"] = constraints.keep_flights + args.get("flights", [])
        if constraints.keep_hotel:
            args["hotels"] = [constraints.keep_hotel] + args.get("hotels", [])
        
        result = optimize_trip(
            flights=args["flights"],
            hotels=args["hotels"],
            total_budget=args["total_budget"],
            strategy=strategy,
        )
        
        # Convert dataclass to dict for JSON serialization
        result_dict = {
            "status": result.status.value,
            "message": result.message,
            "flights": result.flights,
            "hotel": result.hotel,
            "total_cost": result.total_cost,
            "remaining_budget": result.remaining_budget,
            "flight_budget": result.flight_budget,
            "hotel_budget": result.hotel_budget,
            "flight_ratio": result.flight_ratio,
            "hotel_ratio": result.hotel_ratio,
            "component_to_adjust": result.component_to_adjust,
            "keep_flights": result.keep_flights,
            "keep_hotel": result.keep_hotel,
            "error": result.error
        }
        
        # Update constraints based on result
        if result.status == OptimizationStatus.NEED_MORE_OPTIONS:
            constraints.flight_budget = result.flight_budget
            constraints.hotel_budget = result.hotel_budget
            constraints.component_to_adjust = result.component_to_adjust
        
        elif result.status == OptimizationStatus.NEED_CHEAPER_OPTIONS:
            constraints.flight_budget = result.flight_budget
            constraints.hotel_budget = result.hotel_budget
            constraints.component_to_adjust = result.component_to_adjust
            constraints.keep_flights = result.keep_flights
            constraints.keep_hotel = result.keep_hotel
        
        return result_dict
    
    else:
        return {"error": f"Unknown tool: {name}"}

def _format_final_response(result: Dict[str, Any]) -> str:
    """Format the final optimization result for user display."""
    
    flights = result.get("flights", [])
    hotel = result.get("hotel", {})
    total_cost = result.get("total_cost", 0)
    remaining = result.get("remaining_budget", 0)
    
    response = [
        "✅ Trip optimized successfully!\n",
        f"💰 Total Cost: ${total_cost:.2f}",
        f"💵 Remaining Budget: ${remaining:.2f}\n",
        "✈️ Flights:"
    ]
    
    for i, flight in enumerate(flights, 1):
        response.append(f"  Flight {i}: ${flight['cost']:.2f} - {flight.get('airline', 'Unknown')}")
    
    response.extend([
        f"\n🏨 Hotel: ${hotel.get('cost', 0):.2f} - {hotel.get('name', 'Unknown')}",
        f"  Location: {hotel.get('location', 'Unknown')}"
    ])
    
    if result.get("flight_ratio"):
        response.append(f"\n📊 Allocation: {result['flight_ratio']*100:.0f}% flights / {result['hotel_ratio']*100:.0f}% hotels")
    
    return "\n".join(response)