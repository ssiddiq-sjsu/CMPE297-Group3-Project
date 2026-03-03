"""
Deterministic hotel search agent.
Returns hotel options without LLM involvement.
"""

from typing import List, Dict, Any, Optional

from amadeus_hotels import search_hotels_for_trip


def search_hotels(
    destination: str,
    check_in: str,
    check_out: str,
    max_budget: Optional[float] = None,
    min_rating: Optional[float] = None,
    adults: int = 1,
) -> List[Dict[str, Any]]:
    """
    Search for hotels based on criteria.
    Returns a list of hotel dictionaries.
    """
    print(f"\n🏨 Hotel search: {destination}")
    
    try:
        result = search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            max_hotels=10,  # Get more options for filtering
        )
        
        # Filter by budget if specified
        if max_budget is not None and result:
            result = [h for h in result if h.get("total", float('inf')) <= max_budget]
            
        # Filter by rating if specified
        if min_rating is not None and result:
            filtered = []
            for h in result:
                rating = h.get('rating')
                if rating:
                    try:
                        if float(rating) >= min_rating:
                            filtered.append(h)
                    except (ValueError, TypeError):
                        filtered.append(h)
                else:
                    # Keep hotels without rating if we have to
                    filtered.append(h)
            result = filtered
        
        # Sort by price
        result.sort(key=lambda x: x.get("total", float('inf')))
        
        return result
        
    except Exception as e:
        print(f"Error in hotel search: {e}")
        return []


# Alias for backward compatibility
run_agent = search_hotels