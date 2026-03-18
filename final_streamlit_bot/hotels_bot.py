"""
Deterministic hotel search agent with rating support.
Returns hotel options based on rating preferences.
"""

from typing import List, Dict, Any, Optional

from amadeus_hotels import search_hotels_by_rating, search_hotels_for_trip


def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    max_budget: Optional[float] = None,
    min_rating: Optional[int] = None,
    adults: int = 1,
) -> List[Dict[str, Any]]:
    """
    Search for hotels based on criteria with optional rating filter.
    Returns a list of hotel dictionaries.
    """
    print(f"\n🏨 Hotel search: {destination} with min rating {min_rating if min_rating else 'any'}⭐")
    
    try:
        # Use rating filter if specified
        if min_rating and min_rating > 1:
            result = search_hotels_by_rating(
                destination=destination,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
                min_rating=min_rating,
                max_hotels=10,
            )
        else:
            result = search_hotels_for_trip(
                destination=destination,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
                max_hotels=10,
            )
        
        # Filter by budget if specified
        if max_budget is not None and result:
            result = [h for h in result if h.get("total", float('inf')) <= max_budget]
        
        # Sort by price
        result.sort(key=lambda x: x.get("total", float('inf')))
        
        return result
        
    except Exception as e:
        print(f"Error in hotel search: {e}")
        return []


def find_better_hotel(
    destination: str,
    check_in: str,
    check_out: str,
    current_hotel: Dict[str, Any],
    adults: int = 1,
    max_budget: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Find a better hotel based on current selection.
    Tries higher ratings first, then same rating but different options.
    """
    current_rating = current_hotel.get("rating")
    
    # Convert rating to int if possible
    try:
        current_rating_int = int(float(current_rating)) if current_rating else 3
    except (ValueError, TypeError):
        current_rating_int = 3
    
    print(f"\n🔍 Finding better hotel than current ({current_rating_int}⭐)")
    
    # Try higher ratings first
    for target_rating in [5, 4, 3]:
        if target_rating > current_rating_int:
            print(f"Trying {target_rating}⭐ hotels...")
            hotels = search_hotels_by_rating(
                destination=destination,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
                min_rating=target_rating,
                max_hotels=5,
            )
            
            # Filter out current hotel and apply budget
            filtered = []
            for h in hotels:
                if h.get("hotelId") != current_hotel.get("hotelId"):
                    if max_budget is None or h.get("total", 0) <= max_budget:
                        filtered.append(h)
            
            if filtered:
                print(f"Found {len(filtered)} {target_rating}⭐ options")
                return filtered
    
    # If no higher rating, try same rating but different hotels
    print(f"No higher rated hotels found, trying different {current_rating_int}⭐ options...")
    same_rating_hotels = search_hotels_by_rating(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        min_rating=current_rating_int,
        max_hotels=8,
    )
    
    # Filter out current hotel
    filtered = [h for h in same_rating_hotels if h.get("hotelId") != current_hotel.get("hotelId")]
    if max_budget:
        filtered = [h for h in filtered if h.get("total", 0) <= max_budget]
    
    return filtered[:5]  # Return top 5


# Alias for backward compatibility
run_agent = search_hotels