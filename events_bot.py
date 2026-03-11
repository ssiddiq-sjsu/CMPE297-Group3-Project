from predicthq import Client
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderParseError, GeocoderTimedOut
from openai import OpenAI
import json
import os
import random
import time
from datetime import date, timedelta
import requests

"""
PredictHQ API is used to search for events in a city between two dates.
It is used to find events that are happening in a city between two dates.

This code was originally developed by Nic but Craig copy pasted it so the git history is a bit messy.
"""

PHQ_API_KEY = os.getenv("PHQ_API_KEY")
PHQ_BASE_URL = "https://api.predicthq.com/v1"
phq = Client(access_token=PHQ_API_KEY) if PHQ_API_KEY else None
geolocator = Nominatim(user_agent="cmpe297g3")
openai_client = OpenAI()

VALID_CATEGORIES = {
    "concerts",
    "festivals",
    "sports",
    "community",
    "conferences",
    "expos",
    "performing-arts",
    "food-drink"
}

ACTIVITY_TYPE_MAP = {
    "music": "concerts",
    "festival": "festivals",
    "sports": "sports",
    "community": "community",
    "conference": "conferences",
    "expo": "expos",
    "arts": "performing-arts",
    "food": "food-drink",
    "nightlife": "concerts",
    "outdoor": "community",       
}

def get_coordinates(cityname : str):
    try:
        location = geolocator.geocode(cityname)
        if location:
            return location.latitude, location.longitude
        else:
            print(f"Could not find coordinates for '{cityname}'")
            return None, None
    except GeocoderTimedOut:
        print("Request timed out")
        return None, None
    except GeocoderParseError as e:
        print(f"Geocoding error: {e}")
        return None, None

def phq_get(path: str, params: dict = None, timeout: int = 12, retries: int = 2):
    headers = {"Authorization" : f"Bearer {PHQ_API_KEY}"}
    url = f"{PHQ_BASE_URL}{path}"

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.ok:
                return r.json()
            
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep((0.6 * ( 2 ** attempt)) + random.random() * 0.3)
                continue
            return {"_error": {"status":"timeout", "body":f"ReadTimeout after {timeout}s","results":[]}}
        
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                continue
            return {"_error": {"status":"request_exception", "body": str(e),"results":[]}}
    

def events_search(
    city_name : str, 
    start_date : str, end_date : str, 
    categories : list = None, 
    num_events : int =20, 
    radius: int=10) -> dict:
    
    """
    Search PredictHQ for events in a city between start_date and end_date.

    Returns:
    {
        "events": [{"title", "start", "category", "location"}, ...],
        "city": city_name,
    }
    """
    if not PHQ_API_KEY:
        return {"events": [], "city": city_name}

    lat, lon = get_coordinates(city_name)
    if lat is None or lon is None: 
        return {"events":[], "city":city_name, "_error":"Could not geocode city"}
    
    within = f"{radius}km@{lat},{lon}"

    params = {
        "within" : within,
        "limit" : num_events
    }
    if categories:
        valid = [ACTIVITY_TYPE_MAP.get(c.lower(), c.lower()) for c in categories]
        valid = [c for c in valid if c in VALID_CATEGORIES]
        if valid:
            params["category"] = ",".join(valid)
    if start_date:
        params["active.gte"]=start_date
    if end_date:
        params["active.lte"]=end_date
    data = phq_get("/events/", params=params)
    if data.get("_error"):
        return {"events": [], "city": city_name, "_error": data["_error"]}

    events = [
        {
            "title": e.get("title", "Untitled Event"),
            "start": e.get("start", ""),
            "category": e.get("category", ""),
            "location": e.get("geo", {}) or {},
        }
        for e in data.get("results", [])
    ]
    return {"events": events, "city": city_name}

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_events_by_city",
            "description": (
                "Search PredictHQ for events happening in a city between two dates. "
                "Returns a list of events with title, start date, and category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city_name": {
                        "type": "string",
                        "description": "Full city name, e.g. 'Las Vegas' or 'New York City'",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — first day of the trip",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — last day of the trip",
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of activity types to filter by, e.g. "
                            "['music', 'sports', 'food']. Leave empty for all categories."
                        ),
                    },
                    "num_events": {
                        "type": "integer",
                        "description": "Max number of events to fetch (default 20)",
                        "default": 20,
                    },
                },
                "required": ["city_name", "start_date", "end_date"],
            },
        },
    }
]

def run_tool_call(tc) -> dict:
    name = tc.function.name
    args = json.loads(tc.function.arguments or "{}")

    if name == "search_events_by_city":
        return events_search(
            city_name=args["city_name"],
            start_date=args["start_date"],
            end_date=args["end_date"],
            categories=args.get("categories") or [],
            num_events=int(args.get("num_events",20)),
        )

    return {"_error":f"Unknown tool: {name}"}

def run_agent(
        destination:str,
        start_date:str,
        end_date:str,
        activity_types:list=None,
        budget_max:float=None,
) -> list[list[str]] | None:
    
    activity_types = activity_types or []

    system_prompt = (
        "You are a travel events assistant.\n"
        "Rules:\n"
        "- Use the search_events_by_city tool to find real events. Never invent events.\n"
        "- If no events are found, explain that the sandbox may not have data for those dates.\n"
        "- Always show event titles and dates when available.\n"
    )

    user_prompt = (
        f"Find events in {destination} from {start_date} to {end_date}."
    )
    if activity_types:
        user_prompt += f" Preferred activity types: {', '.join(activity_types)}."
    if budget_max:
        user_prompt += f" The traveller's total budget is ${budget_max:.0f}."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        # Tool-call loop (mirrors hotels_bot.py)
        raw_events = []
        while getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tool_result = run_tool_call(tc)
                # Capture the events list from the first successful call
                if not tool_result.get("_error") and tool_result.get("events"):
                    raw_events = tool_result["events"]
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result),
                })

            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.3,
            )
            msg = resp.choices[0].message
            messages.append(msg)

        if not raw_events:
            return None

        return _bucket_events_by_day(raw_events, start_date, end_date)

    except Exception as e:
        print(f"[events_bot] run_agent error: {e}")
        return None

# helper fn
def _bucket_events_by_day(
        events:list[dict],
        start_date:str,
        end_date:str,
) -> list[list[str]]:
    ''' Given flat list of event dicts, return list of lists indexed by trip day'''

    try:
        dep = date.fromisoformat(start_date)
        ret = date.fromisoformat(end_date)
    except ValueError:
        return [[e["title"] for e in events]]
    
    day_count = (ret - dep).days + 1
    buckets: list[list[str]] = [[] for _ in range(day_count)]

    unassigned = []
    for event in events:
        raw_start = (event.get("start") or "")[:10]
        try:
            ev_date = date.fromisoformat(raw_start)
        except ValueError:
            unassigned.append(event["title"])
        else:
            unassigned.append(event["title"])

    for i, title in enumerate(unassigned):
        buckets[i % day_count].append(title)

    return buckets
