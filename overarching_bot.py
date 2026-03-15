"""
Overarching Travel Orchestrator - Hybrid Architecture

Coordinates sub-agents with deterministic optimization but LLM intent handling.
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from flights_bot import search_flights
from airline_codes import get_airline_with_code, resolve_airline_code
from hotels_bot import search_hotels, search_hotels_by_rating, find_better_hotel as find_better_hotel_search

# ==========================================================
# TYPES AND ENUMS
# ==========================================================

class Strategy(str, Enum):
    CHEAPEST_OVERALL = "cheapest_overall"
    SPLURGE_FLIGHT = "splurge_flight"
    SPLURGE_HOTEL = "splurge_hotel"

class OptimizationStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    ERROR = "error"

@dataclass
class OptimizationResult:
    """Result of trip optimization"""
    status: OptimizationStatus
    message: str = ""
    flights: List[Dict[str, Any]] = field(default_factory=list)
    hotel: Optional[Dict[str, Any]] = None
    total_cost: float = 0.0
    remaining_budget: float = 0.0
    flight_budget: Optional[float] = None
    hotel_budget: Optional[float] = None
    flight_ratio: Optional[float] = None
    hotel_ratio: Optional[float] = None
    optimization_history: List[Dict[str, Any]] = field(default_factory=list)
    iterations_used: int = 0  # Add this field


# ==========================================================
# DETERMINISTIC OPTIMIZER
# ==========================================================


def optimize_trip(
    flights: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    total_budget: float,
    strategy: Strategy = Strategy.CHEAPEST_OVERALL,
    max_iterations: int = 5,
) -> OptimizationResult:
    """
    Deterministically optimize flight and hotel selection within budget.
    Always returns the best available options, even if over budget.
    """
    optimization_history = []
    iterations_used = 0  # Track actual iterations used
    
    # Handle empty inputs
    if not flights:
        return OptimizationResult(
            status=OptimizationStatus.ERROR,
            message="No flights available",
            flights=[],
            hotel=None,
            total_cost=0,
            remaining_budget=total_budget,
            optimization_history=[],
            iterations_used=0
        )
    
    if not hotels:
        # Still return flights even without hotels
        cheapest_flights = _get_cheapest_flights(flights)
        total_cost = sum(f.get("cost", 0) for f in cheapest_flights)
        return OptimizationResult(
            status=OptimizationStatus.PARTIAL,
            message="No hotels available",
            flights=cheapest_flights,
            hotel=None,
            total_cost=total_cost,
            remaining_budget=total_budget - total_cost,
            optimization_history=[],
            iterations_used=1
        )
    
    # Sort by cost
    flights_sorted = sorted(flights, key=lambda x: x.get("cost", float('inf')))
    hotels_sorted = sorted(hotels, key=lambda x: x.get("total", float('inf')))
    
    # Get initial allocation based on strategy
    allocation = _get_initial_allocation(strategy)
    flight_ratio, hotel_ratio = allocation["flight"], allocation["hotel"]
    
    best_result = None
    best_total_cost = float('inf')
    
    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        flight_budget = total_budget * flight_ratio
        hotel_budget = total_budget * hotel_ratio
        
        # Find flights within budget
        valid_flights = [f for f in flights_sorted if f.get("cost", float('inf')) <= flight_budget]
        valid_hotels = [h for h in hotels_sorted if h.get("total", float('inf')) <= hotel_budget]
        
        entry = {
            "iteration": iteration + 1,
            "flight_ratio": round(flight_ratio, 2),
            "hotel_ratio": round(hotel_ratio, 2),
            "flight_budget": round(flight_budget, 2),
            "hotel_budget": round(hotel_budget, 2),
            "valid_flights": len(valid_flights),
            "valid_hotels": len(valid_hotels),
        }
        
        # Adjust ratios if no options available
        if not valid_flights and not valid_hotels:
            flight_ratio = min(0.9, flight_ratio + 0.1)
            hotel_ratio = 1 - flight_ratio
            entry["action"] = "adjust_both"
            optimization_history.append(entry)
            continue
        elif not valid_flights:
            flight_ratio = min(0.9, flight_ratio + 0.1)
            hotel_ratio = 1 - flight_ratio
            entry["action"] = "increase_flights"
            optimization_history.append(entry)
            continue
        elif not valid_hotels:
            hotel_ratio = min(0.9, hotel_ratio + 0.1)
            flight_ratio = 1 - hotel_ratio
            entry["action"] = "increase_hotels"
            optimization_history.append(entry)
            continue
        
        # Select options
        selected_flights = _get_cheapest_flights(valid_flights)
        selected_hotel = valid_hotels[0]
        total_cost = sum(f.get("cost", 0) for f in selected_flights) + selected_hotel.get("total", 0)
        
        entry["selected_flights"] = len(selected_flights)
        entry["selected_hotel"] = selected_hotel.get("name", "Unknown")
        entry["total_cost"] = round(total_cost, 2)
        
        # Check if within budget and return immediately
        if total_cost <= total_budget:
            print(f"✅ FOUND SOLUTION after {iteration+1} iterations")
            entry["action"] = "complete"
            entry["remaining_budget"] = round(total_budget - total_cost, 2)
            optimization_history.append(entry)
            return OptimizationResult(
                status=OptimizationStatus.COMPLETE,
                message=f"Found optimal combination after {iteration+1} iterations",
                flights=selected_flights,
                hotel=selected_hotel,
                total_cost=total_cost,
                remaining_budget=total_budget - total_cost,
                flight_budget=flight_budget,
                hotel_budget=hotel_budget,
                flight_ratio=round(flight_ratio, 2),
                hotel_ratio=round(hotel_ratio, 2),
                optimization_history=optimization_history,
                iterations_used=iteration + 1
            )
        
        # If we get here, we're over budget - track best and continue
        if total_cost < best_total_cost:
            best_result = {
                "flights": selected_flights,
                "hotel": selected_hotel,
                "total_cost": total_cost,
                "flight_budget": flight_budget,
                "hotel_budget": hotel_budget,
                "flight_ratio": flight_ratio,
                "hotel_ratio": hotel_ratio,
            }
            best_total_cost = total_cost
            entry["action"] = "found_better (over budget)"
        
        # Adjust ratios for next iteration based on what's expensive
        flight_cost = sum(f.get("cost", 0) for f in selected_flights)
        hotel_cost = selected_hotel.get("total", 0)
        
        if flight_cost > hotel_cost:
            flight_ratio = max(0.2, flight_ratio - 0.05)
            hotel_ratio = 1 - flight_ratio
            entry["action"] = "reduce_flights"
        else:
            hotel_ratio = max(0.2, hotel_ratio - 0.05)
            flight_ratio = 1 - hotel_ratio
            entry["action"] = "reduce_hotels"
        
        optimization_history.append(entry)
    
    # After all iterations, if no solution within budget, return cheapest
    if best_result:
        return OptimizationResult(
            status=OptimizationStatus.PARTIAL,
            message=f"Could not find options within ${total_budget} after {iterations_used} iterations. Showing cheapest available.",
            flights=best_result["flights"],
            hotel=best_result["hotel"],
            total_cost=best_result["total_cost"],
            remaining_budget=total_budget - best_result["total_cost"],
            flight_budget=best_result["flight_budget"],
            hotel_budget=best_result["hotel_budget"],
            flight_ratio=best_result["flight_ratio"],
            hotel_ratio=best_result["hotel_ratio"],
            optimization_history=optimization_history,
            iterations_used=iterations_used
        )
    else:
        # No combination found at all - return absolute cheapest
        cheapest_flights = _get_cheapest_flights(flights_sorted)
        cheapest_hotel = hotels_sorted[0] if hotels_sorted else None
        total_cost = sum(f.get("cost", 0) for f in cheapest_flights)
        if cheapest_hotel:
            total_cost += cheapest_hotel.get("total", 0)
        
        return OptimizationResult(
            status=OptimizationStatus.PARTIAL,
            message=f"No valid combinations found. Showing cheapest available.",
            flights=cheapest_flights,
            hotel=cheapest_hotel,
            total_cost=total_cost,
            remaining_budget=total_budget - total_cost,
            optimization_history=optimization_history,
            iterations_used=iterations_used
        )

def find_better_hotel_option(
    current_hotel: Dict[str, Any],
    hotels_list: List[Dict[str, Any]],
    total_budget: float,
    current_flights_cost: float,
) -> Optional[Dict[str, Any]]:
    """
    Find a better hotel option within budget.
    Prioritizes higher ratings, then different hotels with same rating.
    """
    if not hotels_list or not current_hotel:
        return None
    
    current_rating = current_hotel.get("rating")
    current_cost = current_hotel.get("total", 0)
    
    # Try to get current rating as number
    try:
        current_rating_int = int(float(current_rating)) if current_rating else 3
    except (ValueError, TypeError):
        current_rating_int = 3
    
    remaining_budget = total_budget - current_flights_cost
    
    # Filter hotels within budget
    affordable_hotels = [h for h in hotels_list if h.get("total", float('inf')) <= remaining_budget]
    
    if not affordable_hotels:
        return None
    
    # First, look for higher rated hotels
    higher_rated = []
    for h in affordable_hotels:
        h_rating = h.get("rating")
        try:
            h_rating_int = int(float(h_rating)) if h_rating else 0
            if h_rating_int > current_rating_int and h.get("hotelId") != current_hotel.get("hotelId"):
                higher_rated.append(h)
        except (ValueError, TypeError):
            pass
    
    if higher_rated:
        # Sort by rating (highest first) then by price
        higher_rated.sort(key=lambda x: (-(int(float(x.get("rating", 0)) or 0), x.get("total", float('inf')))))
        return higher_rated[0]
    
    # If no higher rated, try different hotels with same rating
    same_rating_diff = []
    for h in affordable_hotels:
        h_rating = h.get("rating")
        try:
            h_rating_int = int(float(h_rating)) if h_rating else 0
            if h_rating_int == current_rating_int and h.get("hotelId") != current_hotel.get("hotelId"):
                same_rating_diff.append(h)
        except (ValueError, TypeError):
            pass
    
    if same_rating_diff:
        same_rating_diff.sort(key=lambda x: x.get("total", float('inf')))
        return same_rating_diff[0]
    
    return None

def _get_initial_allocation(strategy: Strategy) -> Dict[str, float]:
    """Get initial budget allocation based on strategy."""
    allocations = {
        Strategy.CHEAPEST_OVERALL: {"flight": 0.5, "hotel": 0.5},
        Strategy.SPLURGE_FLIGHT: {"flight": 0.7, "hotel": 0.3},
        Strategy.SPLURGE_HOTEL: {"flight": 0.3, "hotel": 0.7},
    }
    return allocations.get(strategy, {"flight": 0.5, "hotel": 0.5})


def _get_cheapest_flights(flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get the cheapest combination of outbound and return flights."""
    if not flights:
        return []
    
    # Separate outbound and return
    outbound = [f for f in flights if f.get("direction") == "outbound"]
    returns = [f for f in flights if f.get("direction") == "return"]
    
    if outbound and returns:
        # Round trip with both directions
        cheapest_outbound = min(outbound, key=lambda x: x.get("cost", float('inf')))
        cheapest_return = min(returns, key=lambda x: x.get("cost", float('inf')))
        return [cheapest_outbound, cheapest_return]
    elif outbound:
        # One-way or missing returns
        return [min(outbound, key=lambda x: x.get("cost", float('inf')))]
    elif returns:
        # Only returns (unlikely)
        return [min(returns, key=lambda x: x.get("cost", float('inf')))]
    else:
        # Mixed or unspecified direction - just take cheapest overall
        flights_sorted = sorted(flights, key=lambda x: x.get("cost", float('inf')))
        return flights_sorted[:2]  # Take first two as best guess


def parse_user_input(user_input: str) -> Dict[str, Any]:
    """Extract parameters from user input string."""
    params = {
        "origin": None,
        "destination": None,
        "departure_date": None,
        "return_date": None,
        "total_budget": 1000.0,
        "strategy": Strategy.CHEAPEST_OVERALL,
        "prefer_red_eyes": False,
        "adults": 1,
        "max_iterations": 5,
    }
    
    # Extract budget
    budget_match = re.search(r'\$?(\d+(?:\.\d+)?)', user_input)
    if budget_match:
        try:
            params["total_budget"] = float(budget_match.group(1))
        except ValueError:
            pass
    
    # Extract max_iterations
    iter_match = re.search(r'iterations:?\s*(\d+)', user_input, re.IGNORECASE)
    if iter_match:
        try:
            params["max_iterations"] = int(iter_match.group(1))
        except ValueError:
            pass
    
    # Extract strategy
    if "splurge on flight" in user_input.lower() or "splurge flight" in user_input.lower():
        params["strategy"] = Strategy.SPLURGE_FLIGHT
    elif "splurge on hotel" in user_input.lower() or "splurge hotel" in user_input.lower():
        params["strategy"] = Strategy.SPLURGE_HOTEL
    
    # Extract red-eye preference
    if "red-eye" in user_input.lower() or "red eye" in user_input.lower():
        params["prefer_red_eyes"] = True
    
    # Extract dates (basic pattern)
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    dates = re.findall(date_pattern, user_input)
    if len(dates) >= 1:
        params["departure_date"] = dates[0]
    if len(dates) >= 2:
        params["return_date"] = dates[1]
    
    return params


def format_trip_result(result: OptimizationResult, params: Dict[str, Any]) -> str:
    """Format optimization result as a readable string."""
    lines = []
    
    if result.status == OptimizationStatus.COMPLETE:
        lines.append(f"✅ **Trip Optimized Successfully**")
        lines.append(f"(Used {result.iterations_used} iterations)")
    elif result.status == OptimizationStatus.PARTIAL:
        lines.append(f"⚠️ **Partial Results Found**")
        lines.append(f"(Used {result.iterations_used} iterations)")
        lines.append(f"*{result.message}*")  
        lines.append("")  
    else:
        lines.append(f"❌ **No Options Found**")
        lines.append(f"(Used {result.iterations_used} iterations)")
        lines.append(f"*{result.message}*")  
        lines.append("")  
    
    lines.append("")
    lines.append(f"💰 **Total Cost:** \${result.total_cost:.2f}")
    lines.append(f"💵 **Remaining Budget:** \${result.remaining_budget:.2f}")
    
    if result.flight_ratio:
        lines.append(f"📊 **Allocation:** {result.flight_ratio*100:.0f}% flights / {result.hotel_ratio*100:.0f}% hotels")
    
    lines.append("")
    lines.append("✈️ **Flights:**")
    
    # Flights
    if result.flights:
        for i, flight in enumerate(result.flights, 1):
            airline = flight.get("airline", "Unknown")
            airline_code = flight.get("airline_code", "")
            flight_num = flight.get("flight_number", "")
            cost = flight.get("cost", 0)
            dep = flight.get("departure_date", "Unknown")
            arr = flight.get("arrival_date", "Unknown")
            duration = flight.get("duration", "Unknown")
            
            # Format airline display
            if airline_code and airline != airline_code:
                airline_display = f"{airline} ({airline_code})"
            else:
                airline_display = airline
            
            # Create a clean flight entry with proper spacing
            lines.append("")
            lines.append(f"  **Flight {i}:** {airline_display} {flight_num}")
            lines.append(f"    • Depart: {dep}")
            lines.append(f"    • Arrive: {arr}")
            lines.append(f"    • Duration: {duration}")
            lines.append(f"    • Cost: ${cost:.2f}")
    else:
        lines.append("  None found")
    
    lines.append("")
    lines.append("🏨 **Hotel:**")
    
    # Hotel
    if result.hotel:
        hotel = result.hotel
        name = hotel.get("name", "Unknown Hotel")
        cost = hotel.get("total", 0)
        rating = hotel.get("rating", "N/A")
        
        lines.append(f"  **{name}**")
        if rating != "N/A":
            lines.append(f"  • Rating: {rating}⭐")
        lines.append(f"  • Cost: ${cost:.2f}")
    else:
        lines.append("  None found")
    
    return "\n".join(lines)


def _safe_rating_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_total_value(hotel: Dict[str, Any]) -> float:
    try:
        return float(hotel.get("total", float("inf")))
    except (TypeError, ValueError):
        return float("inf")


def _hotel_value_score(hotel: Dict[str, Any]) -> float:
    total = max(_safe_total_value(hotel), 1.0)
    rating = _safe_rating_value(hotel.get("rating"))
    radius_bonus = 1.0 / max(float(hotel.get("searchRadiusKm") or 1), 1.0)
    return (rating * 120.0) / total + radius_bonus


def _hotel_signature(hotel: Optional[Dict[str, Any]]) -> tuple:
    hotel = hotel or {}
    try:
        total = round(float(hotel.get("total", 0) or 0), 2)
    except (TypeError, ValueError):
        total = 0.0
    try:
        rating = round(float(hotel.get("rating", 0) or 0), 1)
    except (TypeError, ValueError):
        rating = 0.0
    return (
        str(hotel.get("hotelId") or "").strip(),
        str(hotel.get("name") or "").strip().lower(),
        total,
        rating,
    )


def _pick_different_hotel(current_hotel: Optional[Dict[str, Any]], hotels: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    current_sig = _hotel_signature(current_hotel)
    for hotel in hotels or []:
        if _hotel_signature(hotel) != current_sig:
            return hotel
    return None


def build_hotel_rankings(hotels: List[Dict[str, Any]], max_budget: float) -> Dict[str, Optional[Dict[str, Any]]]:
    if not hotels:
        return {"cheapest": None, "best_value": None, "best_rating": None}

    affordable = [h for h in hotels if _safe_total_value(h) <= max_budget] or list(hotels)
    cheapest = min(affordable, key=_safe_total_value) if affordable else None
    best_value = max(affordable, key=_hotel_value_score) if affordable else None
    best_rating = max(affordable, key=lambda h: (_safe_rating_value(h.get("rating")), -_safe_total_value(h))) if affordable else None

    return {"cheapest": cheapest, "best_value": best_value, "best_rating": best_rating}

# ==========================================================
# MAIN ORCHESTRATOR
# ==========================================================

def plan_trip(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    total_budget: float = 1000.0,
    strategy: Strategy = Strategy.CHEAPEST_OVERALL,
    prefer_red_eyes: bool = False,
    adults: int = 1,
    max_iterations: int = 5,
    find_better_hotel: bool = False,
    current_hotel: Optional[Dict[str, Any]] = None,
    current_flights: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Main trip planning function.
    Returns a dictionary with results, formatted text, and metadata.
    """
    print(f"\n🎯 Planning trip: {origin} → {destination}")
    print(f"📅 {departure_date} to {return_date}")
    print(f"💰 Budget: ${total_budget}")
    print(f"🔄 Strategy: {strategy.value}")
    print(f"🔁 Max iterations: {max_iterations}")
    if find_better_hotel:
        print(f"🔍 Finding better hotel than current ({current_hotel.get('rating', 'Unknown')}⭐)")
    
    # Search for flights unless we are only swapping the hotel.
    if find_better_hotel and current_flights:
        flights = current_flights
    else:
        flights = search_flights(
            origin_code=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            prefer_red_eyes=prefer_red_eyes,
        )
    
    # Search for hotels
    if find_better_hotel and current_hotel:
        current_flights_cost = sum(f.get("cost", 0) for f in flights)
        remaining_hotel_budget = max(total_budget - current_flights_cost, 0)
        hotels = find_better_hotel_search(
            destination=destination,
            check_in=departure_date,
            check_out=return_date,
            current_hotel=current_hotel,
            adults=adults,
            max_budget=remaining_hotel_budget,
            preference=(current_hotel or {}).get("upgradePreference", "any"),
        )
    else:
        hotels = search_hotels(
            destination=destination,
            check_in=departure_date,
            check_out=return_date,
            adults=adults,
        )
    
    # Optimize. For a hotel swap request, keep the current flights fixed and use
    # the first returned alternative hotel directly so the UI reliably reflects
    # the new hotel instead of silently re-selecting the previous combination.
    if find_better_hotel and current_hotel:
        selected_flights = flights or []
        selected_hotel = _pick_different_hotel(current_hotel, hotels)
        total_cost = sum(f.get("cost", 0) for f in selected_flights) + (selected_hotel.get("total", 0) if selected_hotel else 0)
        status = OptimizationStatus.COMPLETE if selected_hotel else OptimizationStatus.PARTIAL
        message = "Updated hotel selection" if selected_hotel else "No alternative hotel found"
        result = OptimizationResult(
            status=status,
            message=message,
            flights=selected_flights,
            hotel=selected_hotel,
            total_cost=total_cost,
            remaining_budget=total_budget - total_cost,
            flight_ratio=round((sum(f.get("cost", 0) for f in selected_flights) / total_cost), 2) if total_cost else None,
            hotel_ratio=round(((selected_hotel.get("total", 0) if selected_hotel else 0) / total_cost), 2) if total_cost else None,
            optimization_history=[{
                "iteration": 1,
                "action": "swap_hotel",
                "selected_hotel": selected_hotel.get("name", "None") if selected_hotel else "None",
                "total_cost": round(total_cost, 2),
            }],
            iterations_used=1,
        )
    else:
        result = optimize_trip(
            flights=flights,
            hotels=hotels,
            total_budget=total_budget,
            strategy=strategy,
            max_iterations=max_iterations,
        )
    
    # Format response based on what we found
    if not flights and not hotels:
        status_msg = "❌ No flights or hotels found"
        formatted_text = f"""❌ **No Options Found**

No flights or hotels found for your trip.

Suggestions:
• Try different dates
• Try different destinations
• Check if your destination is correct
• Try using airport codes (e.g., SFO, JFK, LAX)

💰 Total Cost: $0.00
💵 Remaining Budget: ${total_budget:.2f}
🔄 Iterations Used: {result.iterations_used}/{max_iterations}"""
    elif not flights:
        status_msg = "⚠️ No flights found"
        formatted_text = f"""⚠️ **No Flights Found**

We found hotels but no flights for your route.

🏨 **Hotels Found:**
{_format_hotels_simple(hotels)}

Suggestions:
• Try different dates
• Check if your origin/destination are correct
• Try nearby airports

💰 Estimated Hotel Cost: ${hotels[0].get('total', 0):.2f} (cheapest)
💵 Remaining Budget: ${total_budget - hotels[0].get('total', 0):.2f}
🔄 Iterations Used: {result.iterations_used}/{max_iterations}"""
    elif not hotels:
        status_msg = "⚠️ No hotels found"
        formatted_text = f"""⚠️ **No Hotels Found**

We found flights but no hotels in your destination.

✈️ **Flights Found:**
{_format_flights_simple(flights)}

Suggestions:
• Try different dates
• Check if your destination is correct
• Try searching for nearby cities

💰 Estimated Flight Cost: ${_get_cheapest_flight_cost(flights):.2f} (cheapest round trip)
💵 Remaining Budget: ${total_budget - _get_cheapest_flight_cost(flights):.2f}
🔄 Iterations Used: {result.iterations_used}/{max_iterations}"""
    else:
        # Both flights and hotels found - use the formatted result from optimizer
        formatted_text = format_trip_result(result, {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
        })
        status_msg = result.message
    
    hotel_rankings = build_hotel_rankings(hotels, total_budget)

    return {
        "formatted": formatted_text,
        "data": {
            "flights": result.flights,
            "hotel": result.hotel,
            "total_cost": result.total_cost,
            "remaining_budget": result.remaining_budget,
            "flight_ratio": result.flight_ratio,
            "hotel_ratio": result.hotel_ratio,
            "status": result.status.value,
            "iterations_used": result.iterations_used,  
            "max_iterations": max_iterations,  
        },
        "optimization_history": result.optimization_history,
        "metadata": {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "total_budget": total_budget,
            "strategy": strategy.value,
            "max_iterations": max_iterations,
            "iterations_used": result.iterations_used,
            "hotel_rankings": hotel_rankings,
        }
    }


def _format_flights_simple(flights: List[Dict[str, Any]]) -> str:
    """Simple flight formatting for when no hotel is found."""
    if not flights:
        return "  None found"
    
    # Get cheapest outbound and return
    outbound = [f for f in flights if f.get("direction") == "outbound"]
    returns = [f for f in flights if f.get("direction") == "return"]
    
    lines = []
    if outbound:
        cheapest_out = min(outbound, key=lambda x: x.get("cost", float('inf')))
        airline = cheapest_out.get("airline", "Unknown")
        airline_code = cheapest_out.get("airline_code", "")
        if airline_code and airline != airline_code:
            airline_display = f"{airline} ({airline_code})"
        else:
            airline_display = airline
        lines.append(f"  • Outbound: {airline_display} {cheapest_out.get('flight_number', '')} - ${cheapest_out.get('cost', 0):.2f}")
    
    if returns:
        cheapest_ret = min(returns, key=lambda x: x.get("cost", float('inf')))
        airline = cheapest_ret.get("airline", "Unknown")
        airline_code = cheapest_ret.get("airline_code", "")
        if airline_code and airline != airline_code:
            airline_display = f"{airline} ({airline_code})"
        else:
            airline_display = airline
        lines.append(f"  • Return: {airline_display} {cheapest_ret.get('flight_number', '')} - ${cheapest_ret.get('cost', 0):.2f}")
    
    if not lines:
        # If no direction specified, just show cheapest
        flights_sorted = sorted(flights, key=lambda x: x.get("cost", float('inf')))
        for i, f in enumerate(flights_sorted[:2], 1):
            airline = f.get("airline", "Unknown")
            airline_code = f.get("airline_code", "")
            if airline_code and airline != airline_code:
                airline_display = f"{airline} ({airline_code})"
            else:
                airline_display = airline
            lines.append(f"  • Option {i}: {airline_display} - ${f.get('cost', 0):.2f}")
    
    return "\n".join(lines)


def _format_hotels_simple(hotels: List[Dict[str, Any]]) -> str:
    """Simple hotel formatting for when no flight is found."""
    if not hotels:
        return "  None found"
    
    lines = []
    for i, h in enumerate(hotels[:3], 1):
        rating = h.get('rating', 'N/A')
        rating_str = f"{rating}⭐" if rating != 'N/A' else 'No rating'
        lines.append(f"  • {h.get('name')}: ${h.get('total', 0):.2f} ({rating_str})")
    
    return "\n".join(lines)


def _get_cheapest_flight_cost(flights: List[Dict[str, Any]]) -> float:
    """Get the cheapest possible round trip cost."""
    if not flights:
        return 0.0
    
    outbound = [f for f in flights if f.get("direction") == "outbound"]
    returns = [f for f in flights if f.get("direction") == "return"]
    
    if outbound and returns:
        return min(f.get("cost", 0) for f in outbound) + min(f.get("cost", 0) for f in returns)
    elif flights:
        return min(f.get("cost", 0) for f in flights)
    return 0.0