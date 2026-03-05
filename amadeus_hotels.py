"""
Hotel search helper module using Amadeus API with rating filtering.
Credentials read from environment variables.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, List, Optional

import requests


AMADEUS_BASE_URL = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_SECRET", "")

if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
    print("⚠️ WARNING: Amadeus credentials not set")


# City name to IATA city code mappings
CITYNAME_TO_CITYCODE: Dict[str, str] = {
    "New York City": "NYC", "New York": "NYC",
    "Miami": "MIA",
    "Los Angeles": "LAX",
    "Orlando": "ORL",
    "San Francisco": "SFO",
    "Las Vegas": "LAS",
    "Washington D.C.": "WAS", "Washington": "WAS",
    "Chicago": "CHI",
    "Honolulu": "HNL",
    "Boston": "BOS",
    "Vancouver": "YVR",
    "Toronto": "YTO",
    "Montreal": "YMQ",
    "San Diego": "SAN",
    "Seattle": "SEA",
    "New Orleans": "MSY",
    "Austin": "AUS",
    "Nashville": "BNA",
    "Philadelphia": "PHL",
    "Denver": "DEN",
    "Atlanta": "ATL",
    "Houston": "HOU",
    "Dallas": "DFW",
}

# Airport code to city code mappings
AIRPORT_TO_CITY_CODE: Dict[str, str] = {
    "JFK": "NYC", "LGA": "NYC", "EWR": "NYC",
    "ORD": "CHI", "MDW": "CHI",
    "DCA": "WAS", "IAD": "WAS", "BWI": "WAS",
    "SFO": "SFO", "OAK": "SFO", "SJC": "SFO",
    "DFW": "DFW", "DAL": "DFW",
    "IAH": "HOU", "HOU": "HOU",
    "MIA": "MIA", "FLL": "MIA", "PBI": "MIA",
    "MCO": "ORL", "SFB": "ORL",
}


def resolve_hotel_city_code(destination: Optional[str]) -> Optional[str]:
    """Resolve destination to IATA city code for hotels."""
    if not destination:
        return None
        
    raw = destination.strip()
    if not raw:
        return None

    # Check exact city name match
    if raw in CITYNAME_TO_CITYCODE:
        return CITYNAME_TO_CITYCODE[raw]

    # Try uppercase for airport/city code
    code = raw.upper()
    return AIRPORT_TO_CITY_CODE.get(code, code)


# Token cache
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def _have_creds() -> bool:
    return bool(AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET)


def amadeus_access_token() -> str:
    """Get (and cache) an Amadeus OAuth token."""
    if not _have_creds():
        raise RuntimeError("Missing Amadeus credentials")

    now = time.time()
    if _token_cache["token"] and now < float(_token_cache["expires_at"]):
        return str(_token_cache["token"])

    url = f"{AMADEUS_BASE_URL}/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_CLIENT_ID,
        "client_secret": AMADEUS_CLIENT_SECRET,
    }
    
    try:
        r = requests.post(url, data=data, timeout=15)
        r.raise_for_status()
        payload = r.json()

        _token_cache["token"] = payload["access_token"]
        _token_cache["expires_at"] = now + int(payload.get("expires_in", 1800)) - 30
        return str(_token_cache["token"])
        
    except Exception as e:
        print(f"Error getting Amadeus token: {e}")
        raise


def amadeus_get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 12,
    retries: int = 2,
) -> Dict[str, Any]:
    """GET wrapper with basic retries."""
    if not _have_creds():
        print("Amadeus credentials not configured")
        return {"data": []}

    try:
        token = amadeus_access_token()
    except Exception as e:
        print(f"Error getting access token: {e}")
        return {"data": []}

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AMADEUS_BASE_URL}{path}"

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.ok:
                return r.json()

            # Retry on 5xx errors
            if 500 <= r.status_code < 600 and attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                time.sleep(sleep_time)
                continue

            print(f"Amadeus API error: {r.status_code}")
            return {"data": []}

        except requests.exceptions.Timeout:
            if attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                time.sleep(sleep_time)
                continue
            print(f"Timeout after {timeout}s")
            return {"data": []}

        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
            return {"data": []}

    return {"data": []}


def get_hotel_ids_by_rating(city_code: str, min_rating: int = 3, max_ids: int = 20) -> List[Dict[str, Any]]:
    """
    Get hotel IDs near the city code filtered by minimum star rating.
    Returns list of hotels with their IDs and ratings.
    """
    # Convert rating to string format expected by Amadeus (1,2,3,4,5)
    rating_param = ",".join([str(r) for r in range(min_rating, 6)])
    
    resp = amadeus_get(
        "/v1/reference-data/locations/hotels/by-city",
        params={
            "cityCode": city_code,
            "radius": 10,
            "radiusUnit": "KM",
            "hotelSource": "ALL",
            "ratings": rating_param,  # Filter by star rating
        },
        timeout=10,
        retries=2,
    )

    hotels = []
    for hotel in resp.get("data", []):
        if isinstance(hotel, dict) and hotel.get("hotelId"):
            hotels.append({
                "hotelId": str(hotel["hotelId"]).strip(),
                "name": hotel.get("name", "Unknown Hotel"),
                "rating": hotel.get("rating"),
                "cityCode": city_code
            })
    
    return hotels[:max_ids]


def get_offers_for_hotel_ids(
    hotel_ids: List[str],
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 5,
) -> List[Dict[str, Any]]:
    """Return offers for the provided hotelIds."""
    if not hotel_ids:
        return []

    # Clean and join hotel IDs
    clean_ids = [hid.strip() for hid in hotel_ids if hid.strip()]
    if not clean_ids:
        return []

    offers = amadeus_get(
        "/v3/shopping/hotel-offers",
        params={
            "hotelIds": ",".join(clean_ids[:20]),  # Limit to 20 IDs
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "adults": adults,
            "roomQuantity": 1,
            "bestRateOnly": "true",
            "currency": "USD",
        },
        timeout=15,
        retries=2,
    )

    results = []
    for entry in offers.get("data", []):
        hotel = entry.get("hotel", {}) or {}
        offer_list = entry.get("offers", []) or []
        
        if not offer_list:
            continue
            
        offer = offer_list[0] or {}
        price = offer.get("price", {}) or {}
        
        # Safely extract total price
        total_str = price.get("total", "0")
        try:
            total = float(total_str)
        except (ValueError, TypeError):
            total = 0.0

        results.append({
            "hotelId": hotel.get("hotelId"),
            "name": hotel.get("name", "Unknown Hotel"),
            "rating": hotel.get("rating"),
            "total": total,
            "currency": price.get("currency", "USD"),
            "offerId": offer.get("id"),
        })

    # Sort by price
    results.sort(key=lambda x: x.get("total", float('inf')))
    return results[:max_hotels]


def search_hotels_by_rating(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    min_rating: int = 3,
    max_hotels: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search for hotels filtered by minimum star rating.
    Returns list of hotel offers.
    """
    print(f"\n🔍 Searching hotels in {destination} with min rating {min_rating}⭐")
    
    city_code = resolve_hotel_city_code(destination)
    if not city_code:
        print(f"Could not resolve city code for: {destination}")
        return []

    # Get hotels with minimum rating
    hotels = get_hotel_ids_by_rating(city_code, min_rating, max_ids=20)
    if not hotels:
        print(f"No hotels found with min rating {min_rating}⭐")
        return []

    # Get hotel IDs for offer search
    hotel_ids = [h["hotelId"] for h in hotels]
    
    offers = get_offers_for_hotel_ids(
        hotel_ids=hotel_ids,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        max_hotels=max_hotels,
    )
    
    # Add rating info to offers
    rating_map = {h["hotelId"]: h["rating"] for h in hotels}
    for offer in offers:
        hotel_id = offer.get("hotelId")
        if hotel_id in rating_map:
            offer["rating"] = rating_map[hotel_id]
    
    print(f"Found {len(offers)} hotel offers with min rating {min_rating}⭐")
    return offers


# Legacy function for backward compatibility
def search_hotels_for_trip(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 5,
) -> List[Dict[str, Any]]:
    """Legacy function - searches all hotels without rating filter."""
    return search_hotels_by_rating(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        min_rating=1,  # Include all hotels
        max_hotels=max_hotels,
    )