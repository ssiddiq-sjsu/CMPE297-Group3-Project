"""
Amadeus flight search: resolve city to IATA and query flight offers.
Uses AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET from env.
"""
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

from amadeus import Client, ResponseError
from airline_codes import resolve_airline_code, get_airline_with_code

# City name to IATA code mappings (fallback if API fails)
CITY_TO_IATA_FALLBACK = {
    "new york": "NYC",
    "new york city": "NYC",
    "nyc": "NYC",
    "los angeles": "LAX",
    "chicago": "CHI",
    "san francisco": "SFO",
    "miami": "MIA",
    "boston": "BOS",
    "washington": "WAS",
    "washington d.c.": "WAS",
    "seattle": "SEA",
    "las vegas": "LAS",
    "orlando": "ORL",
    "denver": "DEN",
    "atlanta": "ATL",
    "dallas": "DFW",
    "houston": "HOU",
    "philadelphia": "PHL",
    "san diego": "SAN",
    "vancouver": "YVR",
    "toronto": "YTO",
    "montreal": "YMQ",
}

# Create client from env
_client_id = os.getenv("AMADEUS_CLIENT_ID")
_client_secret = os.getenv("AMADEUS_SECRET")

if not _client_id or not _client_secret:
    _amadeus = None
    print("⚠️ Amadeus not initialized - missing credentials")
else:
    try:
        _amadeus = Client(client_id=_client_id, client_secret=_client_secret)
        print("✅ Amadeus flight client initialized")
    except Exception as e:
        _amadeus = None
        print(f"❌ Amadeus initialization error: {e}")


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration (e.g. PT2H10M) to human-readable (e.g. 2h 10m)."""
    if not iso_duration:
        return "N/A"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
    if not m:
        return iso_duration
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    parts = []
    if h:
        parts.append(f"{h}h")
    if mn:
        parts.append(f"{mn}m")
    return " ".join(parts) if parts else "0m"


def _normalize_offer(offer: dict, origin_code: str, dest_code: str, direction: str) -> Optional[Dict[str, Any]]:
    """Turn one Amadeus flight offer into a single flight dict for the agent."""
    try:
        if not offer or not offer.get("itineraries"):
            return None
        
        itin = offer["itineraries"][0]
        segs = itin.get("segments") or []
        if not segs:
            return None
            
        seg = segs[0]
        dep = seg.get("departure") or {}
        arr = seg.get("arrival") or {}
        dep_at = dep.get("at", "")
        arr_at = arr.get("at", "")
        
        # Format datetimes for display
        try:
            dep_dt = datetime.fromisoformat(dep_at.replace("Z", "+00:00")) if dep_at else None
            arr_dt = datetime.fromisoformat(arr_at.replace("Z", "+00:00")) if arr_at else None
            dep_str = dep_dt.strftime("%Y-%m-%d %H:%M") if dep_dt else dep_at or "N/A"
            arr_str = arr_dt.strftime("%Y-%m-%d %H:%M") if arr_dt else arr_at or "N/A"
        except (ValueError, TypeError):
            dep_str = dep_at or "N/A"
            arr_str = arr_at or "N/A"
            
        duration = _parse_duration(itin.get("duration", ""))
        carrier_code = seg.get("carrierCode", "")
        number = seg.get("number", "")
        
        # Resolve airline code to full name
        airline_name = resolve_airline_code(carrier_code)
        flight_number = f"{carrier_code}{number}" if carrier_code or number else "N/A"
        
        # Extract price safely
        price_dict = offer.get("price") or {}
        total_str = price_dict.get("total", "0")
        try:
            price = float(total_str)
        except (ValueError, TypeError):
            price = 0.0
            
        return {
            "home_airport": origin_code,
            "destination": dest_code,
            "departure_date": dep_str,
            "arrival_date": arr_str,
            "return_date": arr_str if direction == "return" else None,
            "cost": price,
            "airline": airline_name,
            "airline_code": carrier_code,
            "flight_number": flight_number,
            "duration": duration,
            "direction": direction,
        }
    except Exception as e:
        print(f"Error normalizing flight offer: {e}")
        return None


def city_to_iata(city: str) -> Optional[str]:
    """Resolve a city name to an IATA airport/city code using Amadeus."""
    if not city:
        return None
    
    # First check fallback dictionary (faster and more reliable)
    city_lower = city.lower().strip()
    if city_lower in CITY_TO_IATA_FALLBACK:
        print(f"✅ Using fallback: {city} → {CITY_TO_IATA_FALLBACK[city_lower]}")
        return CITY_TO_IATA_FALLBACK[city_lower]
    
    if not _amadeus:
        print("⚠️ Amadeus not initialized, using fallback only")
        # Try fallback even without API
        for key, value in CITY_TO_IATA_FALLBACK.items():
            if key in city_lower:
                return value
        return None
        
    try:
        # Try with CITY subtype first (more likely to get city code)
        res = _amadeus.reference_data.locations.get(
            keyword=city,
            subType="CITY",
        )
        
        if res.data and len(res.data) > 0:
            iata_code = res.data[0].get("iataCode")
            print(f"✅ Resolved {city} → {iata_code} (via CITY)")
            return iata_code
        
        # If no cities found, try AIRPORT
        res = _amadeus.reference_data.locations.get(
            keyword=city,
            subType="AIRPORT",
        )
        
        if res.data and len(res.data) > 0:
            iata_code = res.data[0].get("iataCode")
            print(f"✅ Resolved {city} → {iata_code} (via AIRPORT)")
            return iata_code
            
        print(f"No data found for city: {city}")
        return None
        
    except ResponseError as e:
        print(f"Amadeus API error in city_to_iata: {e}")
        # Try fallback as last resort
        for key, value in CITY_TO_IATA_FALLBACK.items():
            if key in city_lower:
                return value
        return None
    except Exception as e:
        print(f"Unexpected error in city_to_iata: {e}")
        return None


def search_flights(origin_iata: str, destination_iata: str, date: str) -> List[Dict[str, Any]]:
    """One-way flight offers search. Returns list of raw offers or empty list."""
    if not _amadeus:
        print("⚠️ Amadeus not initialized")
        return []
        
    if not all([origin_iata, destination_iata, date]):
        print("Missing required parameters for flight search")
        return []
        
    try:
        print(f"🔍 Searching flights: {origin_iata} → {destination_iata} on {date}")
        response = _amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin_iata,
            destinationLocationCode=destination_iata,
            departureDate=date,
            adults=1,
            max=20,  # Increased to get more options for filtering
        )
        print(f"Found {len(response.data)} flights")
        return response.data or []
        
    except ResponseError as e:
        print(f"Amadeus API error in search_flights: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error in search_flights: {e}")
        return []


def is_red_eye_flight(departure_datetime: str) -> bool:
    """Check if a flight is a red-eye (between 9PM and 5AM)."""
    if " " not in departure_datetime:
        return False
    try:
        time_str = departure_datetime.split(" ")[1][:5]
        t = datetime.strptime(time_str, "%H:%M")
        hour = t.hour + t.minute / 60
        # Red-eye flights are between 9 PM and 5 AM
        return hour >= 21 or hour < 5
    except (ValueError, IndexError):
        return False


def query_flights(
    origin_code: str,
    destination: str,
    departure_date: str,
    return_date: Optional[str] = None,
    prefer_red_eyes: bool = False,
    max_price: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Query Amadeus for flight offers (outbound and optionally return).
    If prefer_red_eyes=True:
        - Outbound: Only returns red-eye flights (9PM-5AM)
        - Return: Returns all flights (people prefer daytime returns)
    Returns a list of normalized flight dicts.
    """
    if not _amadeus:
        print("⚠️ Amadeus not initialized")
        return []
        
    print(f"\n🔍 Querying flights: {origin_code} → {destination} on {departure_date}")
    if prefer_red_eyes:
        print("🌙 Red-eye preference enabled - filtering outbound for overnight flights")
    
    # Resolve origin if needed
    origin_iata = origin_code
    if not (len(origin_code) == 3 and origin_code.isupper()):
        resolved = city_to_iata(origin_code)
        if resolved:
            origin_iata = resolved
        else:
            print(f"Could not resolve origin: {origin_code}")
            return []
    
    # Resolve destination to IATA if it's a city name
    dest_iata = destination
    if not (len(destination) == 3 and destination.isupper()):
        resolved = city_to_iata(destination)
        if resolved:
            dest_iata = resolved
        else:
            print(f"Could not resolve destination: {destination}")
            return []
    
    # Search outbound flights
    outbound_raw = search_flights(origin_iata, dest_iata, departure_date)
    
    outbound_flights = []
    # Process outbound flights
    for offer in outbound_raw:
        if max_price is not None:
            price_dict = offer.get("price") or {}
            total_str = price_dict.get("total", "0")
            try:
                price = float(total_str)
                if price > max_price:
                    continue
            except (ValueError, TypeError):
                pass
                
        f = _normalize_offer(offer, origin_iata, dest_iata, "outbound")
        if f:
            outbound_flights.append(f)
    
    # Process return flights if requested
    return_flights = []
    if return_date:
        return_raw = search_flights(dest_iata, origin_iata, return_date)
        
        for offer in return_raw:
            if max_price is not None:
                price_dict = offer.get("price") or {}
                total_str = price_dict.get("total", "0")
                try:
                    price = float(total_str)
                    if price > max_price:
                        continue
                except (ValueError, TypeError):
                    pass
                    
            f = _normalize_offer(offer, dest_iata, origin_iata, "return")
            if f:
                return_flights.append(f)
    
    # Apply red-eye filtering if preferred
    if prefer_red_eyes:
        # Filter outbound for red-eye only
        red_eye_outbound = []
        for flight in outbound_flights:
            if is_red_eye_flight(flight.get("departure_date", "")):
                red_eye_outbound.append(flight)
        
        if red_eye_outbound:
            print(f"✅ Found {len(red_eye_outbound)} red-eye outbound flights")
            outbound_flights = red_eye_outbound
        else:
            print("❌ No red-eye outbound flights found")
            outbound_flights = []
        
        # Return flights - keep all (people prefer daytime returns)
        print(f"✅ Keeping all {len(return_flights)} return flights (daytime preferred)")
    
    # Sort outbound by cost
    outbound_flights.sort(key=lambda x: x.get("cost", float('inf')))
    
    # Sort return by cost
    return_flights.sort(key=lambda x: x.get("cost", float('inf')))
    
    # Combine results
    all_flights = outbound_flights + return_flights
    
    print(f"Returning {len(all_flights)} flights ({len(outbound_flights)} outbound, {len(return_flights)} return)")
    return all_flights