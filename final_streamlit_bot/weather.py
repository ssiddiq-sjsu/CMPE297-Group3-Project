"""
Weather info for destination using OpenWeatherMap API
"""
import os
import requests
from datetime import datetime
from typing import Optional, Dict, Any

def get_weather_forecast(city: str, date: str) -> Optional[Dict[str, Any]]:
    """
    Get weather forecast for a city on a specific date
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        return None
    
    # First get city coordinates
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {
        "q": city,
        "limit": 1,
        "appid": api_key
    }
    
    try:
        # Get coordinates
        geo_response = requests.get(geo_url, params=geo_params, timeout=5)
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        
        if not geo_data:
            return None
        
        lat = geo_data[0]["lat"]
        lon = geo_data[0]["lon"]
        
        # Get 5-day forecast (free tier)
        weather_url = "http://api.openweathermap.org/data/2.5/forecast"
        weather_params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "imperial",  # Fahrenheit
            "cnt": 8  # Next 24 hours (3-hour intervals)
        }
        
        weather_response = requests.get(weather_url, params=weather_params, timeout=5)
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        
        # Find forecast closest to arrival date
        target_date = datetime.strptime(date, "%Y-%m-%d")
        closest_forecast = None
        min_diff = float('inf')
        
        for item in weather_data.get("list", []):
            forecast_time = datetime.fromtimestamp(item["dt"])
            diff = abs((forecast_time - target_date).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest_forecast = item
        
        if closest_forecast:
            temp = closest_forecast["main"]["temp"]
            description = closest_forecast["weather"][0]["description"]
            icon = closest_forecast["weather"][0]["icon"]
            
            # Map icon to emoji
            emoji_map = {
                "01d": "☀️", "01n": "🌙",
                "02d": "⛅", "02n": "☁️",
                "03d": "☁️", "03n": "☁️",
                "04d": "☁️", "04n": "☁️",
                "09d": "🌧️", "09n": "🌧️",
                "10d": "🌦️", "10n": "🌦️",
                "11d": "⛈️", "11n": "⛈️",
                "13d": "❄️", "13n": "❄️",
                "50d": "🌫️", "50n": "🌫️"
            }
            weather_emoji = emoji_map.get(icon, "🌡️")
            
            return {
                "temperature": round(temp),
                "description": description.capitalize(),
                "emoji": weather_emoji,
                "humidity": closest_forecast["main"]["humidity"],
                "wind": round(closest_forecast["wind"]["speed"])
            }
        
        return None
        
    except Exception as e:
        print(f"Weather API error: {e}")
        return None


def get_weather_emoji(description: str) -> str:
    """Simple emoji based on weather description"""
    desc = description.lower()
    if "rain" in desc or "drizzle" in desc:
        return "🌧️"
    elif "cloud" in desc:
        return "☁️"
    elif "sun" in desc or "clear" in desc:
        return "☀️"
    elif "snow" in desc:
        return "❄️"
    elif "thunder" in desc:
        return "⛈️"
    elif "fog" in desc or "mist" in desc:
        return "🌫️"
    else:
        return "🌡️"