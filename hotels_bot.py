"""
Deterministic hotel search agent focused primarily on price.
Returns hotel options ordered for the requested price direction.
"""

from typing import List, Dict, Any, Optional

from amadeus_hotels import (
    rank_hotels_for_budget,
    search_hotels_by_rating,
    search_hotels_for_trip,
)

DEFAULT_HOTEL_SEARCH_RADII = [8, 20, 40, 60]
EXPANDED_HOTEL_SEARCH_RADII = [10, 25, 50, 80]


def _safe_total(hotel: Dict[str, Any]) -> float:
    try:
        return float(hotel.get("total", float("inf")))
    except (TypeError, ValueError):
        return float("inf")


def _safe_rating(hotel: Dict[str, Any]) -> float:
    try:
        return float(hotel.get("rating") or 0)
    except (TypeError, ValueError):
        return 0.0


def _value_score(hotel: Dict[str, Any]) -> float:
    total = max(_safe_total(hotel), 1.0)
    return (_safe_rating(hotel) * 120.0) / total


def _hotel_signature(hotel: Dict[str, Any]) -> tuple:
    return (
        str(hotel.get("hotelId") or "").strip(),
        str(hotel.get("name") or "").strip().lower(),
        round(_safe_total(hotel), 2),
        round(_safe_rating(hotel), 1),
    )


def _is_same_hotel(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    if not a or not b:
        return False
    a_id = str(a.get("hotelId") or "").strip()
    b_id = str(b.get("hotelId") or "").strip()
    if a_id and b_id:
        return a_id == b_id
    return _hotel_signature(a) == _hotel_signature(b)


def _prepare_results(hotels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize the result order before it reaches the GUI and annotate useful hotel ranks.
    """
    ordered = sorted(hotels, key=_safe_total)
    if not ordered:
        return ordered

    cheapest_id = ordered[0].get("hotelId")
    best_value = max(ordered, key=_value_score)
    best_rating = max(ordered, key=lambda h: (_safe_rating(h), -_safe_total(h)))
    best_value_id = best_value.get("hotelId")
    best_rating_id = best_rating.get("hotelId")

    for idx, hotel in enumerate(ordered, start=1):
        hotel["priceRank"] = idx
        hotel["isCheapest"] = hotel.get("hotelId") == cheapest_id
        hotel["isBestValue"] = hotel.get("hotelId") == best_value_id
        hotel["isBestRated"] = hotel.get("hotelId") == best_rating_id
        hotel["valueScore"] = round(_value_score(hotel), 4)
    return ordered


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

    Behavior change:
    - searches a wider radius
    - fetches a much larger candidate pool before filtering by budget
    - if nothing matches budget, returns the cheapest near-budget fallback options
    - always returns results sorted by cheapest total price first
    """
    print(f"\n🏨 Hotel search: {destination} with min rating {min_rating if min_rating else 'any'}⭐")

    try:
        common_kwargs = {
            "destination": destination,
            "check_in": check_in,
            "check_out": check_out,
            "adults": adults,
            "max_hotels": 30,
            "max_candidate_hotels": 100,
            "radii_km": DEFAULT_HOTEL_SEARCH_RADII,
        }

        if min_rating and min_rating > 1:
            result = search_hotels_by_rating(min_rating=min_rating, **common_kwargs)
        else:
            result = search_hotels_for_trip(**common_kwargs)

        within_budget, over_budget = rank_hotels_for_budget(result, max_budget)
        if within_budget:
            return _prepare_results(within_budget[:10])

        # Budget rescue pass: search even wider if nothing fits.
        if max_budget is not None:
            print("💸 No hotels within budget from first pass. Expanding area for more options...")
            expanded_kwargs = {
                **common_kwargs,
                "max_hotels": 40,
                "max_candidate_hotels": 140,
                "radii_km": EXPANDED_HOTEL_SEARCH_RADII,
            }
            if min_rating and min_rating > 1:
                result = search_hotels_by_rating(min_rating=min_rating, **expanded_kwargs)
            else:
                result = search_hotels_for_trip(**expanded_kwargs)

            within_budget, over_budget = rank_hotels_for_budget(result, max_budget)
            if within_budget:
                return _prepare_results(within_budget[:10])

            # Nothing fits exactly: return the cheapest close alternatives so the bot can still solve the budget conversation.
            rescued = _prepare_results(over_budget[:5])
            for hotel in rescued:
                hotel["overBudget"] = round(_safe_total(hotel) - max_budget, 2)
            return rescued

        return _prepare_results(result[:10])

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
    preference: str = "any",
) -> List[Dict[str, Any]]:
    """
    Find an alternative hotel based on the user's request.

    preference modes:
    - cheaper: return lower-cost alternatives first
    - different: return a different hotel, ordered by cheapest first
    - more_expensive: return higher-cost alternatives first
    - upgrade / any: treated as a general price-based re-search instead of a star-rating upgrade

    Important behavior:
    - alternative hotel searches do not filter by star rating
    - star rating is kept only as display metadata for the UI
    """
    pref = str(preference or "any").strip().lower()
    current_total = _safe_total(current_hotel)
    print(f"\n🔍 Finding hotel alternative ({pref}) from current ${current_total:.2f}")

    def _filter_results(hotels: List[Dict[str, Any]], require_cheaper: bool = False) -> List[Dict[str, Any]]:
        filtered = []
        for h in hotels:
            if _is_same_hotel(h, current_hotel):
                continue
            total = _safe_total(h)
            if max_budget is not None and total > max_budget:
                continue
            if require_cheaper and total >= current_total:
                continue
            filtered.append(h)
        return _prepare_results(filtered)

    # For "different hotel", keep the minimum rating at 1 star and search widely.
    if pref == "different":
        print("Trying broad hotel swap search with minimum rating 1⭐...")
        hotels = search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            max_hotels=30,
            max_candidate_hotels=140,
            radii_km=EXPANDED_HOTEL_SEARCH_RADII,
        )
        return _filter_results(hotels)[:5]

    if pref == "cheaper":
        print("Trying cheaper hotel search with minimum rating 1⭐...")
        hotels = search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            max_hotels=30,
            max_candidate_hotels=140,
            radii_km=EXPANDED_HOTEL_SEARCH_RADII,
        )
        cheaper = _filter_results(hotels, require_cheaper=True)
        if cheaper:
            # Keep the absolute cheapest option first because the orchestrator
            # selects the first alternative when performing a hotel swap.
            cheaper = sorted(cheaper, key=_safe_total)
            for idx, hotel in enumerate(cheaper, start=1):
                hotel["selectionOrder"] = idx
                hotel["selectionMode"] = "cheapest_first"
            return cheaper[:5]
        fallback = _filter_results(hotels)
        fallback = sorted(fallback, key=_safe_total)
        for idx, hotel in enumerate(fallback, start=1):
            hotel["selectionOrder"] = idx
            hotel["selectionMode"] = "cheapest_first"
        return fallback[:5]

    if pref in {"more_expensive", "expensive", "nicer"}:
        print("Trying more expensive hotel search with minimum rating 1⭐...")
        # Important: fetch a much larger offer pool here. The Amadeus helper sorts
        # by price ascending and then truncates to max_hotels, so using max_hotels=30
        # can accidentally remove every hotel above the current price point.
        hotels = search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            max_hotels=140,
            max_candidate_hotels=140,
            radii_km=EXPANDED_HOTEL_SEARCH_RADII,
        )
        filtered = _filter_results(hotels)
        more_expensive = [h for h in filtered if _safe_total(h) > current_total]
        # Put the priciest option first because the orchestrator picks the first
        # returned hotel when applying the replacement.
        more_expensive = sorted(more_expensive, key=lambda h: _safe_total(h), reverse=True)
        if more_expensive:
            for idx, hotel in enumerate(more_expensive, start=1):
                hotel["selectionOrder"] = idx
                hotel["selectionMode"] = "priciest_first"
            return more_expensive[:5]

        # Do not silently return cheaper hotels for a "more expensive" request.
        # If nothing pricier fits inside the remaining budget, run one more wider
        # uncapped pass so the user can still see the next step up even if it is
        # over the remaining hotel budget.
        print("No pricier hotels found in primary pool. Trying wider uncapped search...")
        wider_hotels = search_hotels_for_trip(
            destination=destination,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            max_hotels=220,
            max_candidate_hotels=220,
            radii_km=[10, 25, 50, 80],
        )
        uncapped = []
        for h in _prepare_results([x for x in wider_hotels if not _is_same_hotel(x, current_hotel)]):
            if _safe_total(h) > current_total:
                h = dict(h)
                if max_budget is not None and _safe_total(h) > max_budget:
                    h["overBudget"] = round(_safe_total(h) - max_budget, 2)
                uncapped.append(h)
        uncapped = sorted(uncapped, key=lambda h: _safe_total(h), reverse=True)
        for idx, hotel in enumerate(uncapped, start=1):
            hotel["selectionOrder"] = idx
            hotel["selectionMode"] = "priciest_first"
        return uncapped[:5]

    # For generic re-searches such as "better hotel" or "upgrade hotel",
    # do not bias toward higher star ratings. Just search broadly again and
    # let price ordering drive the result selection.
    print("Trying broad price-based hotel re-search with no star-rating filter...")
    hotels = search_hotels_for_trip(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        max_hotels=140,
        max_candidate_hotels=140,
        radii_km=EXPANDED_HOTEL_SEARCH_RADII,
    )
    filtered = _filter_results(hotels)
    filtered = sorted(filtered, key=_safe_total)
    for idx, hotel in enumerate(filtered, start=1):
        hotel["selectionOrder"] = idx
        hotel["selectionMode"] = "cheapest_first"
    return filtered[:5]


run_agent = search_hotels
