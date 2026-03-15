"""
Hotel search helper module using Amadeus API with international support.
Credentials read from environment variables.
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


AMADEUS_BASE_URL = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_SECRET", "")

if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
    print("⚠️ WARNING: Amadeus credentials not set")


# City name to IATA city code mappings (expanded for international cities)
CITYNAME_TO_CITYCODE: Dict[str, str] = {
    # US Cities
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

    # International Cities
    "Paris": "PAR",
    "London": "LON",
    "Tokyo": "TYO",
    "Rome": "ROM",
    "Barcelona": "BCN",
    "Madrid": "MAD",
    "Berlin": "BER",
    "Munich": "MUC",
    "Amsterdam": "AMS",
    "Brussels": "BRU",
    "Vienna": "VIE",
    "Prague": "PRG",
    "Budapest": "BUD",
    "Warsaw": "WAW",
    "Stockholm": "STO",
    "Copenhagen": "CPH",
    "Oslo": "OSL",
    "Helsinki": "HEL",
    "Dublin": "DUB",
    "Edinburgh": "EDI",
    "Manchester": "MAN",
    "Liverpool": "LPL",
    "Birmingham": "BHX",
    "Bristol": "BRS",
    "Glasgow": "GLA",
    "Milan": "MIL",
    "Venice": "VCE",
    "Florence": "FLR",
    "Naples": "NAP",
    "Turin": "TRN",
    "Bologna": "BLQ",
    "Geneva": "GVA",
    "Zurich": "ZRH",
    "Basel": "BSL",
    "Lausanne": "QYL",
    "Luxembourg": "LUX",
    "Monaco": "MCM",
    "Lisbon": "LIS",
    "Porto": "OPO",
    "Faro": "FAO",
    "Athens": "ATH",
    "Thessaloniki": "SKG",
    "Istanbul": "IST",
    "Antalya": "AYT",
    "Dubai": "DXB",
    "Abu Dhabi": "AUH",
    "Doha": "DOH",
    "Riyadh": "RUH",
    "Jeddah": "JED",
    "Kuwait City": "KWI",
    "Manama": "BAH",
    "Muscat": "MCT",
    "Tel Aviv": "TLV",
    "Jerusalem": "JRS",
    "Amman": "AMM",
    "Cairo": "CAI",
    "Casablanca": "CMN",
    "Marrakech": "RAK",
    "Tunis": "TUN",
    "Algiers": "ALG",
    "Johannesburg": "JNB",
    "Cape Town": "CPT",
    "Nairobi": "NBO",
    "Lagos": "LOS",
    "Accra": "ACC",
    "Dakar": "DKR",
    "Bangkok": "BKK",
    "Phuket": "HKT",
    "Chiang Mai": "CNX",
    "Singapore": "SIN",
    "Kuala Lumpur": "KUL",
    "Jakarta": "CGK",
    "Bali": "DPS",
    "Manila": "MNL",
    "Ho Chi Minh City": "SGN",
    "Hanoi": "HAN",
    "Phnom Penh": "PNH",
    "Yangon": "RGN",
    "Mumbai": "BOM",
    "Delhi": "DEL",
    "Bangalore": "BLR",
    "Chennai": "MAA",
    "Kolkata": "CCU",
    "Hyderabad": "HYD",
    "Seoul": "SEL",
    "Busan": "PUS",
    "Beijing": "BJS",
    "Shanghai": "SHA",
    "Guangzhou": "CAN",
    "Shenzhen": "SZX",
    "Hong Kong": "HKG",
    "Taipei": "TPE",
    "Sydney": "SYD",
    "Melbourne": "MEL",
    "Brisbane": "BNE",
    "Perth": "PER",
    "Adelaide": "ADL",
    "Auckland": "AKL",
    "Wellington": "WLG",
    "Christchurch": "CHC",
    "Rio de Janeiro": "RIO",
    "Sao Paulo": "SAO",
    "Brasilia": "BSB",
    "Salvador": "SSA",
    "Fortaleza": "FOR",
    "Buenos Aires": "BUE",
    "Santiago": "SCL",
    "Lima": "LIM",
    "Bogota": "BOG",
    "Quito": "UIO",
    "Caracas": "CCS",
    "Panama City": "PTY",
    "San Jose": "SJO",
    "Mexico City": "MEX",
    "Cancun": "CUN",
    "Guadalajara": "GDL",
    "Monterrey": "MTY",
    "Vancouver": "YVR",
    "Toronto": "YTO",
    "Montreal": "YMQ",
    "Calgary": "YYC",
    "Ottawa": "YOW",
    "Quebec City": "YQB",
    "Halifax": "YHZ",
}

# Airport code to city code mappings
AIRPORT_TO_CITY_CODE: Dict[str, str] = {
    # US Airports
    "JFK": "NYC", "LGA": "NYC", "EWR": "NYC",
    "ORD": "CHI", "MDW": "CHI",
    "DCA": "WAS", "IAD": "WAS", "BWI": "WAS",
    "SFO": "SFO", "OAK": "SFO", "SJC": "SFO",
    "DFW": "DFW", "DAL": "DFW",
    "IAH": "HOU", "HOU": "HOU",
    "MIA": "MIA", "FLL": "MIA", "PBI": "MIA",
    "MCO": "ORL", "SFB": "ORL",

    # International Airports
    "CDG": "PAR", "ORY": "PAR", "LBG": "PAR",
    "LHR": "LON", "LGW": "LON", "STN": "LON", "LTN": "LON", "LCY": "LON",
    "NRT": "TYO", "HND": "TYO",
    "FCO": "ROM", "CIA": "ROM",
    "BCN": "BCN",
    "MAD": "MAD",
    "TXL": "BER", "BER": "BER", "SXF": "BER",
    "MUC": "MUC",
    "AMS": "AMS",
    "BRU": "BRU",
    "VIE": "VIE",
    "PRG": "PRG",
    "BUD": "BUD",
    "WAW": "WAW",
    "ARN": "STO", "NYO": "STO",
    "CPH": "CPH",
    "OSL": "OSL",
    "HEL": "HEL",
    "DUB": "DUB",
    "EDI": "EDI",
    "MAN": "MAN",
    "LPL": "LPL",
    "MXP": "MIL", "LIN": "MIL", "BGY": "MIL",
    "VCE": "VCE",
    "FLR": "FLR",
    "GVA": "GVA",
    "ZRH": "ZRH",
    "LIS": "LIS",
    "OPO": "OPO",
    "ATH": "ATH",
    "IST": "IST", "SAW": "IST",
    "DXB": "DXB",
    "AUH": "AUH",
    "DOH": "DOH",
    "RUH": "RUH",
    "JED": "JED",
    "KWI": "KWI",
    "BAH": "BAH",
    "MCT": "MCT",
    "TLV": "TLV",
    "AMM": "AMM",
    "CAI": "CAI",
    "CMN": "CMN",
    "RAK": "RAK",
    "JNB": "JNB",
    "CPT": "CPT",
    "NBO": "NBO",
    "LOS": "LOS",
    "ACC": "ACC",
    "DKR": "DKR",
    "BKK": "BKK", "DMK": "BKK",
    "HKT": "HKT",
    "CNX": "CNX",
    "SIN": "SIN",
    "KUL": "KUL",
    "CGK": "CGK",
    "DPS": "DPS",
    "MNL": "MNL",
    "SGN": "SGN",
    "HAN": "HAN",
    "PNH": "PNH",
    "RGN": "RGN",
    "BOM": "BOM",
    "DEL": "DEL",
    "BLR": "BLR",
    "MAA": "MAA",
    "CCU": "CCU",
    "HYD": "HYD",
    "ICN": "SEL", "GMP": "SEL",
    "PUS": "PUS",
    "PEK": "BJS", "NAY": "BJS",
    "PVG": "SHA", "SHA": "SHA",
    "CAN": "CAN",
    "SZX": "SZX",
    "HKG": "HKG",
    "TPE": "TPE",
    "SYD": "SYD",
    "MEL": "MEL",
    "BNE": "BNE",
    "PER": "PER",
    "ADL": "ADL",
    "AKL": "AKL",
    "WLG": "WLG",
    "CHC": "CHC",
    "GIG": "RIO", "SDU": "RIO",
    "GRU": "SAO", "CGH": "SAO", "VCP": "SAO",
    "BSB": "BSB",
    "SSA": "SSA",
    "FOR": "FOR",
    "EZE": "BUE", "AEP": "BUE",
    "SCL": "SCL",
    "LIM": "LIM",
    "BOG": "BOG",
    "UIO": "UIO",
    "CCS": "CCS",
    "PTY": "PTY",
    "SJO": "SJO",
    "MEX": "MEX", "NLU": "MEX",
    "CUN": "CUN",
    "GDL": "GDL",
    "MTY": "MTY",
    "YVR": "YVR",
    "YYZ": "YTO", "YTZ": "YTO",
    "YUL": "YMQ", "YHU": "YMQ",
    "YYC": "YYC",
    "YOW": "YOW",
    "YQB": "YQB",
    "YHZ": "YHZ",
}

DEFAULT_SEARCH_RADII_KM: List[int] = [8, 20, 40, 60]
MAX_HOTELS_PER_OFFER_CALL = 20


def resolve_hotel_city_code(destination: Optional[str]) -> Optional[str]:
    """Resolve destination to IATA city code for hotels."""
    if not destination:
        return None

    raw = destination.strip()
    if not raw:
        return None

    raw_lower = raw.lower()
    for city_name, code in CITYNAME_TO_CITYCODE.items():
        if city_name.lower() == raw_lower:
            print(f"✅ Resolved city name '{raw}' -> '{code}'")
            return code

    code = raw.upper()
    if code in AIRPORT_TO_CITY_CODE:
        resolved = AIRPORT_TO_CITY_CODE[code]
        print(f"✅ Resolved airport code '{code}' -> '{resolved}'")
        return resolved

    if len(code) == 3 and code.isalpha():
        print(f"✅ Using direct city code: {code}")
        return code

    print(f"❌ Could not resolve destination: {raw}")
    return None


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

    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    payload = r.json()

    _token_cache["token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 1800)) - 30
    return str(_token_cache["token"])


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

            if 500 <= r.status_code < 600 and attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                time.sleep(sleep_time)
                continue

            print(f"Amadeus API error: {r.status_code} - {r.text}")
            return {"data": [], "error": f"HTTP {r.status_code}"}

        except requests.exceptions.Timeout:
            if attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                time.sleep(sleep_time)
                continue
            print(f"Timeout after {timeout}s")
            return {"data": [], "error": "timeout"}

        except requests.exceptions.RequestException as e:
            print(f"Request exception: {e}")
            return {"data": [], "error": str(e)}

    return {"data": []}


def _dedupe_hotel_rows(hotels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for hotel in hotels:
        hotel_id = str(hotel.get("hotelId", "")).strip()
        if not hotel_id:
            continue
        existing = seen.get(hotel_id)
        if existing is None:
            seen[hotel_id] = hotel
            continue
        old_radius = existing.get("searchRadiusKm", 10**9)
        new_radius = hotel.get("searchRadiusKm", 10**9)
        if new_radius < old_radius:
            seen[hotel_id] = hotel
    return list(seen.values())


def get_hotel_ids_by_rating(
    city_code: str,
    min_rating: int = 3,
    max_ids: int = 80,
    radius_km: int = 10,
) -> List[Dict[str, Any]]:
    """
    Get hotel IDs near the city code filtered by minimum star rating.
    Returns list of hotels with their IDs and ratings.
    """
    rating_param = ",".join(str(r) for r in range(min_rating, 6))

    print(f"🔍 Getting hotels with min rating {min_rating}⭐ in {city_code} within {radius_km} km")

    resp = amadeus_get(
        "/v1/reference-data/locations/hotels/by-city",
        params={
            "cityCode": city_code,
            "radius": radius_km,
            "radiusUnit": "KM",
            "hotelSource": "ALL",
            "ratings": rating_param,
        },
        timeout=10,
        retries=2,
    )

    if resp.get("error"):
        print(f"❌ Error getting hotels by rating: {resp['error']}")
        return []

    hotels: List[Dict[str, Any]] = []
    for hotel in resp.get("data", []):
        if isinstance(hotel, dict) and hotel.get("hotelId"):
            hotels.append({
                "hotelId": str(hotel["hotelId"]).strip(),
                "name": hotel.get("name", "Unknown Hotel"),
                "rating": hotel.get("rating"),
                "cityCode": city_code,
                "searchRadiusKm": radius_km,
            })

    print(f"✅ Found {len(hotels)} hotels with min rating {min_rating}⭐ at {radius_km} km")
    return hotels[:max_ids]


def collect_hotel_candidates(
    city_code: str,
    min_rating: int = 1,
    max_ids: int = 80,
    radii_km: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Expand outward from the city center and collect a larger pool of hotels.
    This is the main change that widens the search area.
    """
    radii = radii_km or DEFAULT_SEARCH_RADII_KM
    combined: List[Dict[str, Any]] = []

    for radius in radii:
        batch = get_hotel_ids_by_rating(
            city_code=city_code,
            min_rating=min_rating,
            max_ids=max_ids,
            radius_km=radius,
        )
        combined.extend(batch)
        combined = _dedupe_hotel_rows(combined)
        print(f"📦 Candidate hotel pool: {len(combined)} unique hotels after {radius} km search")
        if len(combined) >= max_ids:
            break

    return combined[:max_ids]


def _chunked(items: List[str], chunk_size: int) -> List[List[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def get_offers_for_hotel_ids(
    hotel_ids: List[str],
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 20,
    best_rate_only: bool = True,
) -> List[Dict[str, Any]]:
    """Return offers for the provided hotelIds using multiple batched API calls."""
    if not hotel_ids:
        return []

    clean_ids = [hid.strip() for hid in hotel_ids if hid and hid.strip()]
    if not clean_ids:
        return []

    print(f"🔍 Getting offers for {len(clean_ids)} hotels")
    results_by_id: Dict[str, Dict[str, Any]] = {}

    for chunk in _chunked(clean_ids, MAX_HOTELS_PER_OFFER_CALL):
        offers = amadeus_get(
            "/v3/shopping/hotel-offers",
            params={
                "hotelIds": ",".join(chunk),
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "adults": adults,
                "roomQuantity": 1,
                "bestRateOnly": "true" if best_rate_only else "false",
                "currency": "USD",
            },
            timeout=20,
            retries=2,
        )

        if offers.get("error"):
            print(f"❌ Error getting offers for chunk: {offers['error']}")
            continue

        for entry in offers.get("data", []):
            hotel = entry.get("hotel", {}) or {}
            offer_list = entry.get("offers", []) or []
            if not offer_list:
                continue

            offer = offer_list[0] or {}
            price = offer.get("price", {}) or {}
            try:
                total = float(price.get("total", "0"))
            except (ValueError, TypeError):
                total = 0.0

            hotel_id = hotel.get("hotelId")
            row = {
                "hotelId": hotel_id,
                "name": hotel.get("name", "Unknown Hotel"),
                "rating": hotel.get("rating"),
                "total": total,
                "currency": price.get("currency", "USD"),
                "offerId": offer.get("id"),
            }

            if hotel_id and (
                hotel_id not in results_by_id
                or total < results_by_id[hotel_id].get("total", float("inf"))
            ):
                results_by_id[hotel_id] = row

    results = list(results_by_id.values())
    results.sort(key=lambda x: x.get("total", float("inf")))
    print(f"✅ Found {len(results)} hotel offers across all search batches")
    return results[:max_hotels]


def search_hotels_by_rating(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    min_rating: int = 3,
    max_hotels: int = 20,
    max_candidate_hotels: int = 80,
    radii_km: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Search for hotels filtered by minimum star rating.
    Widens the search area by collecting hotel candidates across multiple radii
    and then fetching offers in chunks.
    """
    print(f"\n🔍 Searching hotels in {destination} with min rating {min_rating}⭐")

    city_code = resolve_hotel_city_code(destination)
    if not city_code:
        print(f"❌ Could not resolve city code for: {destination}")
        return []

    hotels = collect_hotel_candidates(
        city_code=city_code,
        min_rating=min_rating,
        max_ids=max_candidate_hotels,
        radii_km=radii_km,
    )
    if not hotels:
        print(f"❌ No hotels found with min rating {min_rating}⭐")
        return []

    hotel_ids = [h["hotelId"] for h in hotels]
    offers = get_offers_for_hotel_ids(
        hotel_ids=hotel_ids,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        max_hotels=max_hotels,
    )

    metadata_map = {h["hotelId"]: h for h in hotels}
    for offer in offers:
        hotel_id = offer.get("hotelId")
        if hotel_id in metadata_map:
            meta = metadata_map[hotel_id]
            offer["rating"] = meta.get("rating") or offer.get("rating")
            offer["searchRadiusKm"] = meta.get("searchRadiusKm")

    print(f"✅ Found {len(offers)} hotel offers with min rating {min_rating}⭐")
    return offers


def rank_hotels_for_budget(
    hotels: List[Dict[str, Any]],
    max_budget: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Split hotels into within-budget and over-budget so the caller can still show
    useful fallback options when nothing fits exactly.
    """
    if max_budget is None:
        ordered = sorted(hotels, key=lambda x: x.get("total", float("inf")))
        return ordered, []

    within = [h for h in hotels if h.get("total", float("inf")) <= max_budget]
    over = [h for h in hotels if h.get("total", float("inf")) > max_budget]

    within.sort(key=lambda x: x.get("total", float("inf")))
    over.sort(key=lambda x: x.get("total", float("inf")))
    return within, over


def search_hotels_for_trip(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 20,
    max_candidate_hotels: int = 80,
    radii_km: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Main function - searches all hotels without rating filter."""
    return search_hotels_by_rating(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        min_rating=1,
        max_hotels=max_hotels,
        max_candidate_hotels=max_candidate_hotels,
        radii_km=radii_km,
    )
