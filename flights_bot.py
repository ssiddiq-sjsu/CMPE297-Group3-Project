"""
flights_bot.py

Flight search helper used by server.py.
Uses Amadeus Python SDK (flight_offers_search).

- Credentials are read from environment variables:
    AMADEUS_CLIENT_ID
    AMADEUS_CLIENT_SECRET
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from amadeus import Client, ResponseError

AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "")

# Build client only if creds exist (keeps Flask import-safe)
amadeus = None
if AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET:
    amadeus = Client(client_id=AMADEUS_CLIENT_ID, client_secret=AMADEUS_CLIENT_SECRET)


# GUI destination label -> a primary airport code (flight API needs airport codes)
CITYNAME_TO_PRIMARY_AIRPORT: Dict[str, str] = {
    "New York City": "JFK",
    "Miami": "MIA",
    "Los Angeles": "LAX",
    "Orlando": "MCO",
    "San Francisco": "SFO",
    "Las Vegas": "LAS",
    "Washington D.C.": "IAD",
    "Chicago": "ORD",
    "Honolulu": "HNL",
    "Boston": "BOS",
    "Vancouver": "YVR",
    "Toronto": "YYZ",
    "Montreal": "YUL",
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
    "Houston": "IAH",
    "Dallas": "DFW",
}

# Map common carrier codes to full names (extend as needed)
AIRLINE_NAMES: Dict[str, str] = {
    "UA": "United Airlines",
    "F9": "Frontier Airlines",
    "AA": "American Airlines",
    "DL": "Delta Air Lines",
    "WN": "Southwest Airlines",
    "AS": "Alaska Airlines",
    "B6": "JetBlue",
    "AC": "Air Canada",
    "WS": "WestJet",
    "AY": "Finnair",
    # add more mappings if you like
}


def resolve_destination_airport(destination: Optional[str]) -> Optional[str]:
    if not destination:
        return None
    raw = destination.strip()
    if not raw:
        return None
    if raw in CITYNAME_TO_PRIMARY_AIRPORT:
        return CITYNAME_TO_PRIMARY_AIRPORT[raw]
    return raw.upper()


# ---------- helpers for formatting ----------
def format_time_iso(iso_string: Optional[str]) -> str:
    """
    Convert '2026-04-08T21:35:00' -> 'Apr 8 • 9:35 PM'
    Portable across platforms (avoids %-d).
    """
    if not iso_string:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_string)
        # use %b %d • %I:%M %p, then remove leading zero in day and hour
        s = dt.strftime("%b %d • %I:%M %p")
        # "Apr 08" -> "Apr 8", " 09:05" -> " 9:05"
        s = s.replace(" 0", " ")
        return s
    except Exception:
        return iso_string


def format_duration(iso_duration: Optional[str]) -> str:
    """
    Convert 'PT1H29M' -> '1h 29m'
    """
    if not iso_duration:
        return "N/A"
    try:
        hours_match = re.search(r"(\d+)H", iso_duration)
        minutes_match = re.search(r"(\d+)M", iso_duration)
        h = int(hours_match.group(1)) if hours_match else 0
        m = int(minutes_match.group(1)) if minutes_match else 0
        if h > 0:
            return f"{h}h {m}m" if m > 0 else f"{h}h"
        return f"{m}m"
    except Exception:
        return iso_duration


def format_price_raw(price_str: Any, currency: Optional[str]) -> str:
    """
    Normalize numeric price -> "$63.99" or "63.99 USD" fallback.
    """
    try:
        p = float(price_str)
        # force USD symbol when currency is USD
        if currency and currency.upper() == "USD":
            return f"${p:,.2f}"
        # otherwise include currency code
        cur = (currency or "").upper()
        if cur:
            return f"{p:,.2f} {cur}"
        return f"{p:,.2f}"
    except Exception:
        return str(price_str)


# ---------- Flight search ----------
def search_flights_sdk(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    max_results: int = 3,
    currency: str = "USD",
) -> List[Dict[str, Any]]:
    """
    Calls Amadeus SDK flight offers search (one-way).
    Returns simplified, human-friendly structured results for GUI.
    """
    if not amadeus:
        return []

    try:
        resp = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=departure_date,
            adults=adults,
            max=max_results,
            currencyCode=currency,  # request USD by default
        )

        flights: List[Dict[str, Any]] = []
        for offer in (resp.data or []):
            # Some offers may have multiple itineraries; we'll handle first itinerary
            itinerary = offer.get("itineraries", [])[0]
            segments = itinerary.get("segments", []) or []
            if not segments:
                continue
            first_seg = segments[0]
            last_seg = segments[-1]

            carrier_code = first_seg.get("carrierCode")
            carrier_name = AIRLINE_NAMES.get(carrier_code, carrier_code or "Unknown Carrier")

            raw_departure = first_seg.get("departure", {}).get("at")
            raw_arrival = last_seg.get("arrival", {}).get("at")
            raw_duration = itinerary.get("duration")
            price_obj = offer.get("price", {}) or {}
            price_total = price_obj.get("total")
            price_currency = price_obj.get("currency", currency)

            flights.append({
                "price_raw": price_total,
                "price": format_price_raw(price_total, price_currency),
                "currency": price_currency,
                "carrier_code": carrier_code,
                "carrier": carrier_name,
                "duration": format_duration(raw_duration),
                "departure": format_time_iso(raw_departure),
                "arrival": format_time_iso(raw_arrival),
                "from": first_seg.get("departure", {}).get("iataCode"),
                "to": last_seg.get("arrival", {}).get("iataCode"),
                "segments": len(segments),
                # Keep raw fields if you want to inspect later
                "_raw": {
                    "offer": offer,
                    "itinerary": itinerary,
                }
            })

        # sort by numeric price_raw (if available)
        def _to_float(v: Any) -> float:
            try:
                return float(v or float("inf"))
            except Exception:
                return float("inf")

        flights.sort(key=lambda f: _to_float(f.get("price_raw")))
        return flights

    except ResponseError as e:
        # Print error to server logs to help debugging (don't expose secrets)
        try:
            print("Amadeus ResponseError (flight search):", e.response.result)
        except Exception:
            print("Amadeus ResponseError (flight search) - raw:", str(e))
        return []
    except Exception as e:
        print("Unexpected error in search_flights_sdk:", str(e))
        return []
