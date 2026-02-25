from predicthq import Client
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderParseError, GeocoderTimedOut
import requests

phq_key = "PREDICT_HQ_API_KEY"
phq = Client(access_token=phq_key)
geolocator = Nominatim(user_agent="cmpe297g3")

def get_coordinates(cityname):
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



def events_search(citycode, start_date, end_date, categories, num_events=10, radius=10):
    lat, lon = get_coordinates(citycode)
    within = f"{radius}km{lat},{lon}"
    if isinstance (categories, list):
        categories = dict(categories)

    params = {
        "within" : within,
        "limit" : num_events
    }
    if categories:
        params["categories"]=categories
    if start_date:
        params["active.gte"]=start_date
    if end_date:
        params["active.lte"]=end_date

    headers = {"Authorization": f"Bearer{phq_key}"}
    response = requests.get("https://api.predicthq.com/v1/events/", headers=headers, params=params)
    data = response.json()
    events = [
        {
            "title": e["title"],
            "start": e["start"],
            "category": e["category"],
            "location": e.get("location", {})
        }
        for e in data.get("results", [])
    ]
    return {"events":events,"city":citycode}
