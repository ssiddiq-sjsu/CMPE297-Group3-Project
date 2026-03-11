"""
Deterministic flight search agent.
Returns flight options without LLM involvement.
"""

from typing import List, Dict, Any, Optional

from amadeus_flights import query_flights as amadeus_query_flights


def search_flights(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    prefer_red_eyes: bool = False,
    max_budget: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Search for flights based on criteria.
    Returns a list of flight dictionaries.
    """
    print(f"\n✈️ Flight search: {origin_code} → {destination}")
    
    try:
        result = amadeus_query_flights(
            origin_code=origin_code,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            prefer_red_eyes=prefer_red_eyes,
            max_price=max_budget,
        )
        
        # Ensure we always return a list
        if not isinstance(result, list):
            print(f"Warning: Expected list but got {type(result)}")
            return []
            
        return result
        
    except Exception as e:
        print(f"Error in flight search: {e}")
        return []


# Alias for backward compatibility
run_agent = search_flights