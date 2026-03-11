"""
Events Bot using PredictHQ API
Finds and curates local events during travel dates
Returns raw data only - LLM handles all responses
Fixed venue display and CSS
"""
import re
import os
import json
import random
import time
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderParseError, GeocoderTimedOut

# API Keys
PHQ_API_KEY = os.getenv("PHQ_API_KEY")
if not PHQ_API_KEY:
    print("⚠️ WARNING: PHQ_API_KEY not set - events functionality disabled")
    PHQ_API_KEY = None

PHQ_BASE_URL = "https://api.predicthq.com/v1"

# Initialize geolocator only
geolocator = Nominatim(user_agent="ai-travel-planner")

# Valid PredictHQ categories
VALID_CATEGORIES = {
    "concerts", "festivals", "sports", "community", 
    "conferences", "expos", "performing-arts"
}

# Category display names and emojis (for panel only)
CATEGORY_INFO = {
    "concerts": {"emoji": "🎵", "name": "Concerts & Music"},
    "festivals": {"emoji": "🎪", "name": "Festivals"},
    "sports": {"emoji": "⚽", "name": "Sports"},
    "community": {"emoji": "👥", "name": "Community"},
    "conferences": {"emoji": "💼", "name": "Conferences"},
    "expos": {"emoji": "🏢", "name": "Expos"},
    "performing-arts": {"emoji": "🎭", "name": "Performing Arts"},
}

# Map user-friendly activity types to PredictHQ categories
ACTIVITY_TYPE_MAP = {
    "music": "concerts",
    "concert": "concerts",
    "festival": "festivals",
    "sports": "sports",
    "sport": "sports",
    "game": "sports",
    "match": "sports",
    "community": "community",
    "conference": "conferences",
    "business": "conferences",
    "expo": "expos",
    "exhibition": "expos",
    "arts": "performing-arts",
    "theater": "performing-arts",
    "theatre": "performing-arts",
    "broadway": "performing-arts",
    "comedy": "performing-arts",
    "food": "festivals",
    "drink": "festivals",
    "wine": "festivals",
    "beer": "festivals",
    "restaurant": "festivals",
    "dining": "festivals",
    "nightlife": "concerts",
    "club": "concerts",
    "outdoor": "community",
    "family": "community",
    "kids": "community",
    "holiday": "festivals",
    "christmas": "festivals",
    "new year": "festivals",
    "date night": "performing-arts",
    "romantic": "performing-arts",
    "free": "community",
}


def get_coordinates(city_name: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Convert city name to latitude/longitude coordinates.
    
    Args:
        city_name: Name of city (e.g., "New York City")
        
    Returns:
        Tuple of (latitude, longitude) or (None, None) if not found
    """
    if not city_name:
        return None, None
        
    try:
        print(f"📍 Geocoding: {city_name}")
        location = geolocator.geocode(city_name, timeout=5)
        if location:
            print(f"✅ Found coordinates: {location.latitude}, {location.longitude}")
            return location.latitude, location.longitude
        else:
            print(f"❌ Could not find coordinates for '{city_name}'")
            return None, None
    except GeocoderTimedOut:
        print("⏱️ Geocoding request timed out")
        return None, None
    except GeocoderParseError as e:
        print(f"❌ Geocoding parse error: {e}")
        return None, None
    except Exception as e:
        print(f"❌ Unexpected geocoding error: {e}")
        return None, None


def phq_get(path: str, params: dict = None, timeout: int = 12, retries: int = 2) -> dict:
    """
    Make authenticated GET request to PredictHQ API with retries.
    
    Args:
        path: API endpoint path
        params: Query parameters
        timeout: Request timeout in seconds
        retries: Number of retry attempts
        
    Returns:
        JSON response or error dict
    """
    if not PHQ_API_KEY:
        return {"_error": "PHQ_API_KEY not set", "results": []}
        
    headers = {"Authorization": f"Bearer {PHQ_API_KEY}"}
    url = f"{PHQ_BASE_URL}{path}"
    
    print(f"🔍 PHQ API Request: {url}")

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            
            if r.ok:
                print(f"✅ PHQ API success (attempt {attempt + 1})")
                return r.json()
            
            # Retry on 5xx errors
            if 500 <= r.status_code < 600 and attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                print(f"⚠️ PHQ API error {r.status_code}, retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
                continue
            
            print(f"❌ PHQ API error: {r.status_code}")
            return {"_error": f"HTTP {r.status_code}", "results": []}
            
        except requests.exceptions.Timeout:
            if attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                print(f"⏱️ PHQ timeout, retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
                continue
            print(f"❌ PHQ timeout after {timeout}s")
            return {"_error": "timeout", "results": []}
            
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                sleep_time = (0.5 * (2 ** attempt)) + random.random() * 0.5
                print(f"⚠️ PHQ request error: {e}, retrying...")
                time.sleep(sleep_time)
                continue
            print(f"❌ PHQ request error: {e}")
            return {"_error": str(e), "results": []}
    
    return {"_error": "unknown", "results": []}


def map_activity_to_category(activity: str) -> Optional[str]:
    """
    Map user-friendly activity type to PredictHQ category.
    
    Args:
        activity: User input like "music", "sports", "food"
        
    Returns:
        PredictHQ category or None if not mappable
    """
    if not activity:
        return None
        
    activity_lower = activity.lower().strip()
    
    # Direct match
    if activity_lower in VALID_CATEGORIES:
        return activity_lower
    
    # Map via dictionary
    for key, category in ACTIVITY_TYPE_MAP.items():
        if key in activity_lower or activity_lower in key:
            return category
    
    return None


def search_events_by_category(
    city_name: str,
    start_date: str,
    end_date: str,
    category: str,
    radius: int = 10,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search for events in a specific category.
    
    Args:
        city_name: City name
        start_date: ISO date YYYY-MM-DD
        end_date: ISO date YYYY-MM-DD
        category: PredictHQ category
        radius: Search radius in km
        limit: Max events per category
        
    Returns:
        List of events
    """
    if category not in VALID_CATEGORIES:
        return []
    
    # Get coordinates
    lat, lon = get_coordinates(city_name)
    if lat is None or lon is None:
        return []
    
    # Build parameters
    within = f"{radius}km@{lat},{lon}"
    
    params = {
        "within": within,
        "category": category,
        "active.gte": start_date,
        "active.lte": end_date,
        "sort": "rank",  # Sort by popularity
        "limit": limit,
    }
    
    data = phq_get("/events/", params=params)
    
    if data.get("_error") or not data.get("results"):
        return []
    
    # Parse and enrich events
    events = []
    for e in data.get("results", []):
        # Extract rank (popularity score)
        rank = e.get("rank", 0)
        
        # Get location data
        location = e.get("location", [])
        venue = None
        city = None
        
        if isinstance(location, list) and len(location) >= 2:
            city = location[1] if location[1] and location[1] != "United States" else None
            # Try to get venue from labels or other fields
            if e.get("entities"):
                for entity in e.get("entities", []):
                    if entity.get("type") == "venue":
                        venue = entity.get("name")
                        break
        
        # Get event-specific labels
        labels = e.get("labels", [])
        
        # Format date nicely
        start = e.get("start", "")
        end = e.get("end", "")
        
        # Determine if it's an all-day event
        is_all_day = False
        if start and end:
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                # If it spans a full day or more
                is_all_day = (end_dt - start_dt).days >= 1
            except:
                pass
        
        # Format time string
        time_str = "All day" if is_all_day else ""
        if start and not is_all_day and len(start) > 16:
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                time_str = dt.strftime("%I:%M %p").lstrip("0")
            except:
                time_str = start[11:16]
        
        events.append({
            "id": e.get("id"),
            "title": e.get("title", "Untitled Event"),
            "description": e.get("description", ""),
            "start": start,
            "end": end,
            "start_date": start[:10] if start else "",
            "start_time": time_str,
            "category": category,
            "category_emoji": CATEGORY_INFO.get(category, {}).get("emoji", "📅"),
            "category_name": CATEGORY_INFO.get(category, {}).get("name", category),
            "labels": labels,
            "venue": venue,
            "city": city,
            "location": location,
            "rank": rank,
            "popularity": rank,
            "is_all_day": is_all_day,
            "predicted_event": e.get("predicted_event", False),
        })
    
    return events


def deduplicate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate events by title and date.
    """
    seen = set()
    unique = []
    
    for event in events:
        # Create unique key
        title = event.get("title", "")
        start = event.get("start", "")[:10]
        key = f"{title}|{start}"
        
        if key not in seen:
            seen.add(key)
            unique.append(event)
    
    return unique


def curate_events(
    events_by_category: Dict[str, List[Dict[str, Any]]],
    max_total: int = 8,
    max_per_day: int = 3,
    exclude_ids: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Curate events across categories to return best overall.
    
    Args:
        events_by_category: Dict mapping category to list of events
        max_total: Maximum total events to return
        max_per_day: Maximum events per day
        exclude_ids: Event IDs to exclude
        
    Returns:
        Curated list of events
    """
    exclude_ids = exclude_ids or []
    
    # Flatten all events with category info
    all_events = []
    for category, events in events_by_category.items():
        for event in events:
            if event.get("id") not in exclude_ids:
                event["_category"] = category
                all_events.append(event)
    
    # Sort by rank (popularity) descending
    all_events.sort(key=lambda x: x.get("rank", 0), reverse=True)
    
    # Deduplicate
    all_events = deduplicate_events(all_events)
    
    # Group by date for per-day limiting
    events_by_date = {}
    for event in all_events:
        date_key = event.get("start_date", "")
        if date_key:
            if date_key not in events_by_date:
                events_by_date[date_key] = []
            events_by_date[date_key].append(event)
    
    # Select top events respecting per-day limit
    selected = []
    dates_used = {}
    
    for event in all_events:
        if len(selected) >= max_total:
            break
            
        date_key = event.get("start_date", "")
        if not date_key:
            # Events without dates go to the end
            continue
            
        current_count = dates_used.get(date_key, 0)
        
        if current_count < max_per_day:
            selected.append(event)
            dates_used[date_key] = current_count + 1
    
    # Add any remaining spots with events without dates
    if len(selected) < max_total:
        for event in all_events:
            if event not in selected and event.get("id") not in exclude_ids:
                if len(selected) < max_total:
                    selected.append(event)
    
    return selected


def get_popularity_label(rank: int, category: str, labels: List[str] = None, predicted: bool = False) -> str:
    """Get variety in popularity labels based on rank and category."""
    labels = labels or []
    
    if rank > 90:
        if category == "concerts":
            return " • 🎸 Sold Out Show"
        elif category == "sports":
            return " • 🏆 Championship Game"
        elif category == "food-drink":
            return " • ⭐ Michelin Recommended"
        elif category == "performing-arts":
            return " • 🎭 Broadway Hit"
        elif category == "festivals":
            return " • 🎪 Major Festival"
        else:
            return " • 🔥 Must-See Event"
    elif rank > 80:
        if category == "concerts":
            return " • 🎤 Top Artist"
        elif category == "sports":
            return " • 🏀 Playoff Game"
        elif category == "food-drink":
            return " • 🍷 Critics' Pick"
        elif category == "performing-arts":
            return " • 🎟️ Selling Fast"
        elif category == "festivals":
            return " • 🎉 Popular Festival"
        else:
            return " • ⭐ Highly Rated"
    elif rank > 70:
        if category == "concerts":
            return " • 🎸 Popular Show"
        elif category == "sports":
            return " • ⚽ Big Match"
        elif category == "food-drink":
            return " • 🍽️ Foodie Favorite"
        elif category == "performing-arts":
            return " • 🎭 Great Reviews"
        elif category == "festivals":
            return " • 🎊 Local Favorite"
        else:
            return " • 📈 Trending Now"
    elif rank > 50:
        if "free" in str(labels).lower():
            return " • 🆓 Free Entry"
        elif "family" in str(labels).lower() or "kids" in str(labels).lower():
            return " • 👨‍👩‍👧 Family Friendly"
        elif "outdoor" in str(labels).lower():
            return " • 🌳 Outdoor"
        else:
            return " • 👍 Recommended"
    else:
        if predicted:
            return " • 🆕 Just Announced"
        elif "community" in category:
            return " • 👥 Community Event"
        else:
            return " • 📅 Local Favorite"

def format_events_panel(events: List[Dict[str, Any]], destination: str) -> str:
    """
    Format events for display in the main panel.
    Returns clean HTML string with venue names (not coordinates).
    """

    def is_coordinate(text: Any) -> bool:
        """
        Detect if a string looks like latitude/longitude coordinates.
        """
        if not text:
            return False
        
        # Convert to string if it's a number
        if isinstance(text, (int, float)):
            text = str(text)
        
        text = text.strip()

        # Match patterns like:
        # 40.6718747
        # -73.98234
        # 40.6718747,-73.98234
        coord_pattern = r'^-?\d+(\.\d+)?(,\s*-?\d+(\.\d+)?)?$'
        return bool(re.match(coord_pattern, text))

    if not events:
        return f"<p>No events found in {destination} for these dates.</p>"
    
    # Group by date
    events_by_date = {}
    for event in events:
        date_key = event.get("start_date", "unknown")
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        events_by_date[date_key].append(event)
    
    # Sort dates
    sorted_dates = sorted([d for d in events_by_date.keys() if d != "unknown"])
    
    lines = [f"<h4>🎉 Events in {destination}</h4>"]
    
    for date_key in sorted_dates:
        try:
            dt = datetime.fromisoformat(date_key)
            formatted_date = dt.strftime("%A, %B %d")
        except:
            formatted_date = date_key
        
        lines.append(f"<div class='event-day'>")
        lines.append(f"<strong>{formatted_date}</strong>")
        
        for event in events_by_date[date_key]:
            emoji = event.get("category_emoji", "📅")
            title = event.get("title", "Unknown Event")
            time_str = event.get("start_time", "")
            venue = event.get("venue", "")
            city = event.get("city", "")
            rank = event.get("rank", 0)
            category = event.get("category", "")
            labels = event.get("labels", [])
            
            # Determine readable location - filter out coordinates
            location_text = ""
            if venue and not is_coordinate(venue):
                location_text = venue
            elif city and city != "United States" and not is_coordinate(city):
                location_text = city
            
            # Build compact display
            display = f"{emoji} <strong>{title}</strong>"
            
            # Format time
            if time_str and time_str not in ["All day", "00:00", ""]:
                # Try to format time nicely (convert 23:30 to 11:30 PM)
                try:
                    if ":" in time_str and len(time_str) <= 5:
                        t = datetime.strptime(time_str, "%H:%M")
                        time_str = t.strftime("%I:%M %p").lstrip("0")
                except:
                    pass
                display += f" • {time_str}"
            elif time_str == "All day":
                display += f" • All day"
            
            # Add location if we have readable text
            if location_text:
                display += f" • 📍 {location_text}"
            
            # Add popularity label (make sure this function exists)
            display += get_popularity_label(rank, category, labels, event.get("predicted_event", False))
            
            lines.append(f"<div class='event-item'>{display}</div>")
        
        lines.append("</div>")
    
    # Add unknown date events if any (limit to 2)
    if "unknown" in events_by_date and events_by_date["unknown"]:
        lines.append("<div class='event-day'>")
        lines.append("<strong>Other events</strong>")
        
        for event in events_by_date["unknown"][:2]:
            emoji = event.get("category_emoji", "📅")
            title = event.get("title", "Unknown Event")
            lines.append(f"<div class='event-item'>{emoji} {title}</div>")
        
        lines.append("</div>")
    
    return "\n".join(lines)

def search_events(
    destination: str,
    start_date: str,
    end_date: str,
    preferences: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
    max_events: int = 8,
) -> Dict[str, Any]:
    """
    Main event search function - returns RAW DATA only.
    NO LLM RESPONSES - just structured event data.
    
    Args:
        destination: Destination city
        start_date: Trip start date (YYYY-MM-DD)
        end_date: Trip end date (YYYY-MM-DD)
        preferences: Optional list of preferred activity types
        exclude_ids: Event IDs to exclude
        max_events: Maximum total events to return
        
    Returns:
        Dict with raw events data and metadata for LLM to process
    """
    print(f"\n🎯 Event Search: {destination} from {start_date} to {end_date}")
    if preferences:
        print(f"🎯 Preferences: {preferences}")
    
    # Map preferences to categories
    categories_to_search = []
    search_terms = []
    
    if preferences:
        for pref in preferences:
            mapped = map_activity_to_category(pref)
            if mapped and mapped not in categories_to_search:
                categories_to_search.append(mapped)
                search_terms.append(pref)
                print(f"🎯 Mapped '{pref}' → '{mapped}'")
    
    # If no preferences or mapping failed, search all categories
    if not categories_to_search:
        categories_to_search = list(VALID_CATEGORIES)
        search_terms = ["events"]
        print(f"🎯 No preferences specified, searching all categories")
    
    # Search each category
    events_by_category = {}
    total_raw = 0
    
    for category in categories_to_search:
        print(f"🔍 Searching category: {category}")
        events = search_events_by_category(
            city_name=destination,
            start_date=start_date,
            end_date=end_date,
            category=category,
            limit=15,
        )
        if events:
            events_by_category[category] = events
            total_raw += len(events)
            print(f"✅ Found {len(events)} events in {category}")
    
    # Curate events
    curated_events = curate_events(
        events_by_category, 
        max_total=max_events, 
        max_per_day=3,
        exclude_ids=exclude_ids,
    )
    
    # Format panel HTML (for display only)
    panel_html = format_events_panel(curated_events, destination)
    
    # Return RAW DATA - NO LLM RESPONSES
    return {
        "events": curated_events,
        "panel_html": panel_html,
        "total": len(curated_events),
        "total_raw": total_raw,
        "categories_searched": categories_to_search,
        "categories_found": list(set(e.get("category", "") for e in curated_events)),
        "search_terms": search_terms,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "date_range": f"{start_date} to {end_date}",
        "event_ids": [e.get("id") for e in curated_events],
        "has_events": len(curated_events) > 0,
    }