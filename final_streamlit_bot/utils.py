"""
Utility functions for the travel planner.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


def parse_budget(text: str) -> Optional[float]:
    """Extract budget from text."""
    match = re.search(r'\$?(\d+(?:\.\d{2})?)', text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def parse_dates(text: str) -> Dict[str, Optional[str]]:
    """Extract dates from text."""
    date_pattern = r'(\d{4}-\d{2}-\d{2})'
    dates = re.findall(date_pattern, text)
    
    result = {
        "departure_date": None,
        "return_date": None
    }
    
    if len(dates) >= 1:
        result["departure_date"] = dates[0]
    if len(dates) >= 2:
        result["return_date"] = dates[1]
    
    return result


def parse_cities(text: str) -> Dict[str, Optional[str]]:
    """Extract origin and destination from text."""
    # Look for patterns like "from X to Y"
    pattern = r'from\s+([A-Za-z\s]+?)\s+to\s+([A-Za-z\s]+?)(?:\s+on|\s*$|\.)'
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return {
            "origin": match.group(1).strip(),
            "destination": match.group(2).strip()
        }
    
    return {"origin": None, "destination": None}


def format_currency(amount: float) -> str:
    """Format amount as currency."""
    return f"${amount:,.2f}"


def validate_dates(departure: str, return_date: str) -> bool:
    """Validate that return date is after departure date."""
    try:
        dep = datetime.strptime(departure, "%Y-%m-%d")
        ret = datetime.strptime(return_date, "%Y-%m-%d")
        return ret > dep
    except (ValueError, TypeError):
        return False


def get_default_dates(days_ahead: int = 30, trip_length: int = 7) -> Dict[str, str]:
    """Get default departure and return dates."""
    today = datetime.now()
    departure = today + timedelta(days=days_ahead)
    return_date = departure + timedelta(days=trip_length)
    
    return {
        "departure": departure.strftime("%Y-%m-%d"),
        "return": return_date.strftime("%Y-%m-%d")
    }


def safe_json_parse(json_str: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string."""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."