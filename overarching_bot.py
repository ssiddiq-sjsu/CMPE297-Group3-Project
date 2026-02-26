"""
Overarching ReAct Travel Orchestrator.

Coordinates sub-agents:
- flights_bot
- hotels_bot

Features:
- Intelligent budget optimization that checks feasibility before adjusting
- Handles edge cases where cheaper options may not exist
- Automatic re-running of agents when needed
- Full debug history tracking
- AI commentary on trip plans
- Respects user's max_iterations slider for total optimizer calls
"""

import json
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from openai import OpenAI

from flights_bot import run_agent as run_flights_agent
from hotels_bot import run_agent as run_hotels_agent

client = OpenAI()

# Global list to store optimization iterations (for debug)
optimization_history = []


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
# TRIP COMMENTARY FUNCTION
# ==========================================================

def generate_trip_commentary(flights: List[Dict[str, Any]], hotels: List[Dict[str, Any]], 
                             total_budget: float, total_cost: float, strategy: str,
                             optimization_iterations: int, max_allowed_calls: int) -> str:
    """
    Generate AI commentary on the trip plan with recommendations.
    
    Args:
        flights: List of flight dictionaries
        hotels: List of hotel dictionaries
        total_budget: Total trip budget
        total_cost: Total cost of selected options
        strategy: Strategy string (e.g., "cheapest_overall")
        optimization_iterations: Number of iterations used
        max_allowed_calls: Maximum allowed optimizer calls
    """
    
    client = OpenAI()
    
    # Calculate some metrics
    flight_costs = [f["cost"] for f in flights] if flights else []
    avg_flight_cost = sum(flight_costs) / len(flight_costs) if flight_costs else 0
    hotel_cost = hotels[0]["cost"] if hotels else 0
    
    budget_usage = (total_cost / total_budget) * 100 if total_budget > 0 else 0
    
    # Format strategy name for display
    strategy_display = strategy.replace('_', ' ').title() if strategy else "Cheapest Overall"
    
    # Check if we found a solution or failed
    if not flights and not hotels:
        # Failure case
        prompt = f"""
        You are a travel advisor. The system tried {max_allowed_calls} times to find a flight+hotel combination within ${total_budget} budget but failed.
        
        Provide a helpful message (2-3 sentences) suggesting what the user could do:
        - Increase budget (suggest a specific amount like 20-30%)
        - Try different dates (mid-week is usually cheaper)
        - Be more flexible with preferences
        - Use more optimization iterations (currently {max_allowed_calls})
        
        Be encouraging and specific. Start with "🤖 Travel Advisor:"
        """
    else:
        # Success case
        prompt = f"""
        You are a travel advisor analyzing a trip plan. Provide a brief, helpful commentary (2-3 sentences) on:
        
        Trip Details:
        - Total Budget: ${total_budget}
        - Total Cost: ${total_cost} ({budget_usage:.1f}% of budget)
        - Strategy Used: {strategy_display}
        - Optimization Attempts Used: {optimization_iterations} out of {max_allowed_calls} allowed
        
        Flight Info:
        - Number of flights: {len(flights)}
        - Average flight cost: ${avg_flight_cost:.2f}
        - Cheapest flight: ${min(flight_costs) if flight_costs else 0}
        
        Hotel Info:
        - Hotel cost: ${hotel_cost}
        
        Based on this data, provide ONE of the following:
        1. If the trip fits well within budget (under 80%): Comment that it was easy to find options and suggest they could splurge on something like a better hotel or direct flights.
        2. If it's close to budget (80-95%): Suggest specific actions like finding cheaper hotels or flights, or slightly increasing budget.
        3. If under budget (below 60%): Recommend upgrading something (better hotel, direct flights, etc.).
        4. If very tight (over 95%): Suggest finding cheaper options or increasing budget.
        
        Keep it conversational and helpful. Don't use markdown. Be concise. Start with "🤖 Travel Advisor:"
        """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful travel advisor. Provide brief, actionable advice."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        if not flights and not hotels:
            return f"🤖 Travel Advisor: I couldn't find options within your ${total_budget} budget after {max_allowed_calls} attempts. Try increasing your budget by 20-30% or adjusting your travel dates."
        else:
            return f"🤖 Travel Advisor: Trip planned successfully using {optimization_iterations} optimization attempts. Use the chat to ask for recommendations!"


# ==========================================================
# INTELLIGENT OPTIMIZER
# ==========================================================

def optimize_trip(
    flights: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    total_budget: float,
    strategy: Strategy,
    max_iterations: int = 3,  # Internal optimizer iterations per call
) -> OptimizationResult:
    """
    Optimize flight and hotel selection within budget.
    Uses intelligent decision-making to avoid infinite loops.
    
    Args:
        flights: List of available flight options
        hotels: List of available hotel options
        total_budget: Total trip budget
        strategy: Budget allocation strategy
        max_iterations: Maximum number of internal optimization attempts (default 3)
    """
    
    # Clear global history at start
    global optimization_history
    optimization_history = []
    
    # Sort by cost for consistent selection and feasibility checking
    flights_sorted = sorted(flights, key=lambda x: x["cost"])
    hotels_sorted = sorted(hotels, key=lambda x: x["cost"])
    
    if not flights_sorted or not hotels_sorted:
        missing = []
        if not flights_sorted:
            missing.append("flights")
        if not hotels_sorted:
            missing.append("hotels")
        
        # Log error to history
        optimization_history.append({
            "iteration": 0,
            "action": "error",
            "error": f"Missing {', '.join(missing)} results",
            "flights_available": len(flights_sorted),
            "hotels_available": len(hotels_sorted)
        })
        
        return OptimizationResult(
            status=OptimizationStatus.ERROR,
            error=f"Missing {', '.join(missing)} results"
        )
    
    # Get initial allocation based on strategy
    allocation = _get_initial_allocation(strategy)
    flight_ratio, hotel_ratio = allocation["flight"], allocation["hotel"]
    
    for iteration in range(max_iterations):
        flight_budget = total_budget * flight_ratio
        hotel_budget = total_budget * hotel_ratio
        
        # Find options within budget
        valid_flights = [f for f in flights_sorted if f["cost"] <= flight_budget]
        valid_hotels = [h for h in hotels_sorted if h["cost"] <= hotel_budget]
        
        # Log this iteration
        history_entry = {
            "iteration": iteration + 1,
            "flight_ratio": round(flight_ratio, 2),
            "hotel_ratio": round(hotel_ratio, 2),
            "flight_budget": round(flight_budget, 2),
            "hotel_budget": round(hotel_budget, 2),
            "valid_flights_count": len(valid_flights),
            "valid_hotels_count": len(valid_hotels),
            "total_flights_available": len(flights_sorted),
            "total_hotels_available": len(hotels_sorted)
        }
        
        # CASE 1: No flights found - need to increase flight budget
        if not valid_flights:
            new_flight_ratio = min(0.9, flight_ratio + 0.05)
            history_entry["action"] = "need_more_flight_budget"
            history_entry["message"] = f"No flights found within ${flight_budget:.2f}"
            history_entry["new_flight_ratio"] = round(new_flight_ratio, 2)
            optimization_history.append(history_entry)
            
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
            history_entry["action"] = "need_more_hotel_budget"
            history_entry["message"] = f"No hotels found within ${hotel_budget:.2f}"
            history_entry["new_hotel_ratio"] = round(new_hotel_ratio, 2)
            optimization_history.append(history_entry)
            
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
        
        # Add selection details to history
        history_entry["selected_flights"] = [
            {
                "airline": f.get("airline", "Unknown"),
                "flight_number": f.get("flight_number", "N/A"),
                "cost": f.get("cost", 0)
            } for f in selected_flights
        ]
        history_entry["selected_hotel"] = {
            "name": selected_hotel.get("name", "Unknown"),
            "cost": selected_hotel.get("cost", 0)
        }
        history_entry["total_cost"] = round(total_cost, 2)
        
        # CASE 3: Within budget - success!
        if total_cost <= total_budget:
            print("="*50)
            print(f"FOUND SOLUTION after {iteration+1} iterations:")
            print(f"Flights: {selected_flights}")
            print(f"Hotel: {selected_hotel}")
            print(f"Total: {total_cost}")
            print("="*50)
            
            history_entry["action"] = "complete"
            history_entry["message"] = f"Found solution within budget"
            history_entry["remaining_budget"] = round(total_budget - total_cost, 2)
            optimization_history.append(history_entry)
            
            return OptimizationResult(
                status=OptimizationStatus.COMPLETE,
                flights=selected_flights,
                hotel=selected_hotel,
                total_cost=total_cost,
                remaining_budget=total_budget - total_cost,
                message=f"Found optimized solution after {iteration+1} iterations",
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
        
        history_entry["flight_cost"] = round(flight_cost, 2)
        history_entry["hotel_cost"] = round(hotel_cost, 2)
        history_entry["cheaper_flights_exist"] = cheaper_flights_exist
        history_entry["cheaper_hotels_exist"] = cheaper_hotels_exist
        
        # INTELLIGENT DECISION LOGIC
        if flight_cost > hotel_cost:
            # Flights are the expensive component
            if cheaper_flights_exist:
                # We CAN make flights cheaper - reduce flight allocation
                new_flight_ratio = max(0.1, flight_ratio - 0.05)
                history_entry["action"] = "reduce_flights"
                history_entry["message"] = f"Total ${total_cost:.2f} exceeds budget. Reducing flights to find cheaper options."
                history_entry["new_flight_ratio"] = round(new_flight_ratio, 2)
                optimization_history.append(history_entry)
                
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
                history_entry["action"] = "reduce_hotels"
                history_entry["message"] = f"Total ${total_cost:.2f} exceeds budget and no cheaper flights. Reducing hotels instead."
                history_entry["new_hotel_ratio"] = round(new_hotel_ratio, 2)
                optimization_history.append(history_entry)
                
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
                history_entry["action"] = "reduce_hotels"
                history_entry["message"] = f"Total ${total_cost:.2f} exceeds budget. Reducing hotels to find cheaper options."
                history_entry["new_hotel_ratio"] = round(new_hotel_ratio, 2)
                optimization_history.append(history_entry)
                
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
                history_entry["action"] = "reduce_flights"
                history_entry["message"] = f"Total ${total_cost:.2f} exceeds budget and no cheaper hotels. Reducing flights instead."
                history_entry["new_flight_ratio"] = round(new_flight_ratio, 2)
                optimization_history.append(history_entry)
                
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
    optimization_history.append({
        "iteration": max_iterations,
        "action": "error",
        "message": f"No valid combination within budget after {max_iterations} attempts"
    })
    
    return OptimizationResult(
        status=OptimizationStatus.ERROR,
        error=f"No valid combination within budget after {max_iterations} attempts"
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
# TOOL DEFINITIONS
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
                    },
                    "max_iterations": {
                        "type": "number", 
                        "description": "Maximum number of internal optimization attempts (default: 3)",
                        "optional": True
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
    Respects user's max_iterations slider for total optimizer calls.
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
7. Stop when optimize_trip returns complete OR after max_iterations total optimizer calls

Default to {Strategy.CHEAPEST_OVERALL.value} strategy unless user specifies otherwise.
""",
        },
        {"role": "user", "content": user_input},
    ]
    
    constraints = BudgetConstraints()
    
    # Extract max_iterations from user_input (default to 3)
    max_optimizer_calls = 3
    match = re.search(r'max_iterations:?\s*(\d+)', user_input, re.IGNORECASE)
    if match:
        max_optimizer_calls = int(match.group(1))
    
    # Extract total_budget from user_input for failure case
    total_budget = 0
    budget_match = re.search(r'\$(\d+)', user_input)
    if budget_match:
        total_budget = int(budget_match.group(1))
    
    print(f"\n📊 Max optimizer calls allowed: {max_optimizer_calls}")
    print(f"💰 Total budget: ${total_budget}")
    optimizer_call_count = 0
    
    while optimizer_call_count < max_optimizer_calls:
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
                
                # For optimize_trip, ensure max_iterations is set
                if name == "optimize_trip" and "max_iterations" not in args:
                    args['max_iterations'] = max_optimizer_calls
                
                # Execute the appropriate tool with constraints
                result = _execute_tool(name, args, constraints)
                
                print(f"Result: {json.dumps(result, default=str, indent=2)[:500]}...")
                
                # Add the tool response message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
                
                # Count optimizer calls
                if name == "optimize_trip":
                    optimizer_call_count += 1
                    print(f"📊 Optimizer call #{optimizer_call_count} of {max_optimizer_calls}")
                    
                    # Check if we're done
                    if result.get("status") == OptimizationStatus.COMPLETE.value:
                        # Get the strategy from args
                        strategy = args.get("strategy", Strategy.CHEAPEST_OVERALL.value)
                        
                        # Generate AI commentary
                        commentary = generate_trip_commentary(
                            flights=result.get("flights", []),
                            hotels=[result.get("hotel", {})] if result.get("hotel") else [],
                            total_budget=args.get("total_budget", 0),
                            total_cost=result.get("total_cost", 0),
                            strategy=strategy,
                            optimization_iterations=len(optimization_history),
                            max_allowed_calls=max_optimizer_calls
                        )
                        
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
                            },
                            "optimization_history": optimization_history,
                            "commentary": commentary
                        }, default=str)
            
        except Exception as e:
            return f"Error in orchestration: {str(e)}"
    
    # If we've used all optimizer calls without success
    print(f"\n❌ No solution found after {max_optimizer_calls} optimizer calls")
    
    # Generate failure commentary with the actual budget
    failure_commentary = generate_trip_commentary(
        flights=[],
        hotels=[],
        total_budget=total_budget,
        total_cost=0,
        strategy=Strategy.CHEAPEST_OVERALL.value,  # Added .value here
        optimization_iterations=0,
        max_allowed_calls=max_optimizer_calls
    )
    
    return json.dumps({
        "formatted": "No solution found within budget limits.",
        "data": {
            "flights": [],
            "hotel": {},
            "total_cost": 0,
            "remaining_budget": 0,
            "flight_ratio": None,
            "hotel_ratio": None
        },
        "optimization_history": optimization_history,
        "commentary": failure_commentary
    }, default=str)

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
        
        # Get max_iterations from args or use default 3
        max_iterations = args.get("max_iterations", 3)
        
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
            max_iterations=max_iterations  # Internal optimizer iterations
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