"""hotels_bot.py

Hotel search helper module used by the Flask backend (server.py).

- Credentials are read from environment variables:
    AMADEUS_CLIENT_ID
    AMADEUS_CLIENT_SECRET
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
    raise ValueError("AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET are not set")


# ---------- Destination mappings ----------
# Your GUI uses human-readable destination strings (e.g., "New York City").
# Hotels API primarily wants an IATA city code; we map where possible.
CITYNAME_TO_CITYCODE: Dict[str, str] = {
    "New York City": "NYC",
    "Miami": "MIA",
    "Los Angeles": "LAX",
    "Orlando": "ORL",
    "San Francisco": "SFO",
    "Las Vegas": "LAS",
    "Washington D.C.": "WAS",
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
    "Savannah": "SAV",
    "Philadelphia": "PHL",
    "San Antonio": "SAT",
    "Denver": "DEN",
    "Charleston": "CHS",
    "Atlanta": "ATL",
    "Houston": "HOU",
    "Dallas": "DFW",
}

# If you ever pass airport codes instead of city names, map them too.
AIRPORT_TO_CITY_CODE: Dict[str, str] = {
    "JFK": "NYC",
    "LGA": "NYC",
    "EWR": "NYC",
    "ORD": "CHI",
    "MDW": "CHI",
    "DCA": "WAS",
    "IAD": "WAS",
    "BWI": "WAS",
    "SFO": "SFO",
    "OAK": "SFO",
    "SJC": "SFO",
    "DFW": "DFW",
    "DAL": "DFW",
    "IAH": "HOU",
    "HOU": "HOU",
    "MIA": "MIA",
    "FLL": "MIA",
    "PBI": "MIA",
    "MCO": "ORL",
    "SFB": "ORL",
}


def resolve_hotel_city_code(destination: Optional[str]) -> Optional[str]:
    """Resolve GUI destination / airport code / city code into an IATA city code for hotels."""
    if not destination:
        return None
    raw = destination.strip()
    if not raw:
        return None

    # Exact GUI label -> city code
    if raw in CITYNAME_TO_CITYCODE:
        return CITYNAME_TO_CITYCODE[raw]

    # Otherwise treat as code-like input
    code = raw.upper()
    # Airport -> city code, else assume it's already a city code
    return AIRPORT_TO_CITY_CODE.get(code, code)


# ---------- Amadeus REST helpers ----------
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}


def _have_creds() -> bool:
    return bool(AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET)


def amadeus_access_token() -> str:
    """Get (and cache) an Amadeus OAuth token."""
    if not _have_creds():
        raise RuntimeError(
            "Missing Amadeus credentials. Set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET environment variables."
        )

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
    """GET wrapper with basic retries and a consistent error shape."""
    try:
        token = amadeus_access_token()
    except Exception as e:
        return {"_error": {"status": "missing_credentials", "body": str(e)}, "data": []}

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{AMADEUS_BASE_URL}{path}"

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.ok:
                return r.json()

            # Retry transient 5xx
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep((0.6 * (2**attempt)) + random.random() * 0.3)
                continue

            return {"_error": {"status": r.status_code, "body": r.text}, "data": []}

        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                time.sleep((0.6 * (2**attempt)) + random.random() * 0.3)
                continue
            return {"_error": {"status": "timeout", "body": f"ReadTimeout after {timeout}s"}, "data": []}

        except requests.exceptions.RequestException as e:
            return {"_error": {"status": "request_exception", "body": str(e)}, "data": []}

    return {"_error": {"status": "unknown", "body": "Unknown error"}, "data": []}


# ---------- Hotels API ----------
def get_hotel_ids(city_code: str, max_ids: int = 10) -> List[str]:
    """Return hotelIds near the city code."""
    resp = amadeus_get(
        "/v1/reference-data/locations/hotels/by-city",
        params={
            "cityCode": city_code,
            "radius": 10,
            "radiusUnit": "KM",
            "hotelSource": "ALL",
        },
        timeout=10,
        retries=2,
    )

    if resp.get("_error"):
        return []

    ids: List[str] = []
    for h in (resp.get("data", []) or []):
        if isinstance(h, dict) and h.get("hotelId"):
            ids.append(str(h["hotelId"]).strip())
    return ids[:max_ids]


def get_offers_for_hotel_ids(
    hotel_ids: List[str],
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 3,
) -> List[Dict[str, Any]]:
    """Return cheapest/best offers for the provided hotelIds."""
    if not hotel_ids:
        return []

    offers = amadeus_get(
        "/v3/shopping/hotel-offers",
        params={
            "hotelIds": ",".join([hid.strip() for hid in hotel_ids if hid.strip()]),
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "adults": adults,
            "roomQuantity": 1,
            "bestRateOnly": "true",
            "currency": "USD",
        },
        timeout=12,
        retries=2,
    )

    if offers.get("_error"):
        print("\n\n offers error: ", offers.get("_error"))
        return []

    results: List[Dict[str, Any]] = []
    for entry in (offers.get("data", []) or []):
        hotel = entry.get("hotel", {}) or {}
        offer_list = entry.get("offers", []) or []
        if not offer_list:
            continue
        offer = offer_list[0] or {}
        price = offer.get("price", {}) or {}

        results.append(
            {
                "hotelId": hotel.get("hotelId"),
                "name": hotel.get("name"),
                "rating": hotel.get("rating"),
                "total": price.get("total"),
                "currency": price.get("currency"),
                "offerId": offer.get("id"),
            }
        )

    def to_float(x: Any) -> float:
        try:
            return float(x)
        except Exception:
            return float("inf")

    results.sort(key=lambda r: to_float(r.get("total")))
    return results[:max_hotels]


def search_hotels_for_trip(
    destination: str,
    check_in: str,
    check_out: str,
    adults: int = 1,
    max_hotels: int = 3,
) -> List[Dict[str, Any]]:
    """Main entry used by server.py: destination + dates -> list of hotel offers."""
    city_code = resolve_hotel_city_code(destination)
    if not city_code:
        print("\n\n no city code found")
        return []

    hotel_ids = get_hotel_ids(city_code, max_ids=10)
    if not hotel_ids:
        print("\n\n no hotel ids found")
        return []

    return get_offers_for_hotel_ids(
        hotel_ids=hotel_ids,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        max_hotels=max_hotels,
    )