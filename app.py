"""
Streamlit GUI for Travel Orchestrator with Chat Interface

Users can:
- View initial trip plan
- Ask questions about the current plan
- Request modifications that trigger re-optimization
- View detailed optimization journey when debug is enabled
- Save and load past trips from history
- Get AI commentary and recommendations
- Control total optimization attempts via slider
- Change budget to specific amounts via chat
- Change strategy via chat
- Combine multiple changes in one message
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import your existing modules
from overarching_bot import run_overarching_bot, Strategy
from flights_bot import run_agent as run_flights_agent
from hotels_bot import run_agent as run_hotels_agent

# Page configuration
st.set_page_config(
    page_title="AI Travel Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# CHAT PROCESSING FUNCTIONS - DEFINED FIRST
# ==========================================================

def process_chat_message(message: str, current_result: dict, search_params: dict) -> dict:
    """Process user chat message and return appropriate response."""
    
    message_lower = message.lower()
    
    # Check for recommendation requests first
    recommendation_keywords = ['cheaper hotel', 'better hotel', 'cheaper flight', 'direct flight', 
                              'red-eye', 'upgrade', 'recommend', 'suggestion']
    if any(keyword in message_lower for keyword in recommendation_keywords):
        return handle_recommendation_request(message_lower, current_result, search_params)
    
    # Check for modification requests
    if is_modification_request(message_lower):
        return handle_modification_request(message_lower, search_params)
    
    # Otherwise handle as Q&A
    return answer_question(message_lower, current_result, search_params)


def is_modification_request(message: str) -> bool:
    """Determine if the message is requesting a plan modification."""
    modification_keywords = [
        'cheaper', 'expensive', 'better', 'different', 'change',
        'increase', 'decrease', 'raise', 'lower', 'adjust',
        'modify', 'update', 'red-eye', 'red eye', 'overnight',
        'budget', 'price', 'cost', 'more', 'less', 'strategy',
        'splurge', 'cheapest'
    ]
    return any(keyword in message for keyword in modification_keywords)


def handle_modification_request(message: str, search_params: dict) -> dict:
    """Handle modification requests by updating search parameters.
       Can handle multiple changes in one message (budget + strategy + preference)."""
    
    response = {
        "type": "modification", 
        "message": "", 
        "budget": None, 
        "preference": None, 
        "strategy": None
    }
    
    message_lower = message.lower()
    changes_made = []
    
    # === STRATEGY DETECTION ===
    if 'cheapest overall' in message_lower or 'cheapest' in message_lower:
        response['strategy'] = 'cheapest_overall'
        changes_made.append("strategy changed to Cheapest Overall")
        
    elif 'splurge on flights' in message_lower or 'splurge flight' in message_lower or 'more on flights' in message_lower:
        response['strategy'] = 'splurge_flight'
        changes_made.append("strategy changed to Splurge on Flights")
        
    elif 'splurge on hotel' in message_lower or 'splurge hotel' in message_lower or 'more on hotel' in message_lower:
        response['strategy'] = 'splurge_hotel'
        changes_made.append("strategy changed to Splurge on Hotel")
    
    # === BUDGET DETECTION - Specific dollar amount ===
    amount_match = re.search(r'\$?\s*(\d+)(?:\s* dollars?)?', message)
    if amount_match:
        # Check if it's a budget change (contains budget-related words)
        if any(word in message_lower for word in ['budget', 'increase', 'set', 'change', 'to', 'spend', 'total']):
            new_budget = float(amount_match.group(1))
            response['budget'] = new_budget
            changes_made.append(f"budget set to ${new_budget:.0f}")
    
    # === BUDGET DETECTION - Percentage based (only if no specific amount found) ===
    if response['budget'] is None:
        if 'cheaper' in message_lower or 'lower budget' in message_lower or 'less' in message_lower:
            current_budget = search_params.get('total_budget', 1500)
            new_budget = current_budget * 0.8
            response['budget'] = new_budget
            changes_made.append(f"budget reduced to ${new_budget:.0f}")
            
        elif 'more expensive' in message_lower or 'higher budget' in message_lower or 'increase' in message_lower:
            current_budget = search_params.get('total_budget', 1500)
            new_budget = current_budget * 1.2
            response['budget'] = new_budget
            changes_made.append(f"budget increased to ${new_budget:.0f}")
    
    # === PREFERENCE DETECTION ===
    if 'red-eye' in message_lower or 'red eye' in message_lower or 'overnight' in message_lower:
        if 'prefer' in message_lower or 'yes' in message_lower or 'true' in message_lower or 'want' in message_lower:
            response['preference'] = True
            changes_made.append("red-eye flights preferred")
        elif 'avoid' in message_lower or 'no' in message_lower or 'false' in message_lower:
            response['preference'] = False
            changes_made.append("red-eye flights avoided")
    
    # === DATE MODIFICATIONS ===
    if 'different date' in message_lower or 'change date' in message_lower:
        response['message'] = "Please use the date pickers above to change your travel dates."
        return response
    
    # === BUILD RESPONSE MESSAGE ===
    if changes_made:
        if len(changes_made) == 1:
            response['message'] = f"🔄 {changes_made[0].capitalize()}. Searching again..."
        else:
            # Combine multiple changes
            changes_text = ", ".join(changes_made[:-1]) + " and " + changes_made[-1]
            response['message'] = f"🔄 {changes_text.capitalize()}. Searching again..."
    else:
        response['message'] = "I can help you modify your trip. Try asking for 'increase budget to $2000' or 'switch to splurge on flights'."
    
    return response


def handle_recommendation_request(message: str, current_result: dict, search_params: dict) -> dict:
    """Handle requests for recommendations (cheaper hotel, better flight, etc.)"""
    
    response = {"type": "recommendation", "message": "", "action": None, "params": {}}
    
    # Cheaper hotel recommendation
    if 'cheaper hotel' in message or 'cheaper accommodation' in message:
        current_hotel = current_result.get('hotel', {})
        if current_hotel and isinstance(current_hotel, dict):
            current_hotel_cost = current_hotel.get('cost', 0)
            if current_hotel_cost > 0:
                target_budget = current_hotel_cost * 0.8  # 20% cheaper
                response['action'] = 'search_hotels'
                response['params'] = {'max_budget': target_budget}
                response['message'] = f"Looking for hotels under ${target_budget:.0f} (20% cheaper than current)..."
            else:
                response['message'] = "No hotel in current plan to compare. Try searching for a new trip first."
        else:
            response['message'] = "No hotel in current plan. Try searching for a new trip first."
    
    # Better hotel recommendation
    elif 'better hotel' in message or 'nicer hotel' in message or 'upgrade hotel' in message:
        current_hotel = current_result.get('hotel', {})
        if current_hotel and isinstance(current_hotel, dict):
            current_hotel_cost = current_hotel.get('cost', 0)
            remaining = current_result.get('remaining_budget', 0)
            if remaining > 0:
                target_budget = current_hotel_cost + (remaining * 0.5)  # Use half remaining budget
                response['action'] = 'search_hotels'
                response['params'] = {'max_budget': target_budget, 'min_rating': 4}
                response['message'] = f"Looking for better hotels up to ${target_budget:.0f}..."
            else:
                response['message'] = "You don't have remaining budget for a hotel upgrade. Try increasing your total budget first."
        else:
            response['message'] = "No hotel in current plan. Try searching for a new trip first."
    
    # Cheaper flights recommendation
    elif 'cheaper flight' in message:
        current_flights = current_result.get('flights', [])
        if current_flights:
            current_flight_costs = [f.get('cost', 0) for f in current_flights]
            total_flight_cost = sum(current_flight_costs)
            target_budget = total_flight_cost * 0.8  # 20% cheaper
            response['action'] = 'search_flights'
            response['params'] = {'max_budget': target_budget}
            response['message'] = f"Looking for flights under ${target_budget:.0f} total..."
        else:
            response['message'] = "No flights in current plan. Try searching for a new trip first."
    
    # Direct flights recommendation
    elif 'direct flight' in message or 'non-stop' in message:
        response['action'] = 'search_flights'
        response['params'] = {'prefer_direct': True}
        response['message'] = "Searching for direct flight options..."
    
    # Red-eye recommendation
    elif 'red-eye' in message or 'overnight' in message:
        response['action'] = 'search_flights'
        response['params'] = {'prefer_red_eyes': True}
        response['message'] = "Looking for red-eye flight options..."
    
    # Budget increase recommendation
    elif 'increase budget' in message or 'more budget' in message:
        current_budget = search_params.get('total_budget', 1500)
        new_budget = current_budget * 1.2  # 20% increase
        response['action'] = 'adjust_budget'
        response['params'] = {'new_budget': new_budget}
        response['message'] = f"Increasing budget to ${new_budget:.0f} to find better options..."
    
    # General recommendation
    elif 'recommend' in message or 'suggestion' in message:
        budget_usage = (current_result.get('total_cost', 0) / search_params.get('total_budget', 1)) * 100
        if budget_usage < 60:
            response['message'] = "You're well under budget! I recommend upgrading to a better hotel or splurging on direct flights."
        elif budget_usage < 80:
            response['message'] = "You have some room in your budget. Consider a slightly nicer hotel or better flight times."
        elif budget_usage < 95:
            response['message'] = "You're close to budget. I can help find cheaper options if you'd like."
        else:
            response['message'] = "You're at your budget limit. Try asking for 'cheaper flights' or 'cheaper hotels' to save money."
    
    return response


def answer_question(message: str, current_result: dict, search_params: dict) -> dict:
    """Answer questions about the current trip plan."""
    
    flights = current_result.get('flights', [])
    hotel = current_result.get('hotel', {})
    if not isinstance(hotel, dict):
        hotel = {}
    total_cost = current_result.get('total_cost', 0)
    
    # Flight questions
    if 'flight' in message:
        if not flights:
            return {"type": "answer", "message": "No flights in the current plan."}
        
        if 'how long' in message or 'duration' in message:
            if len(flights) >= 1:
                duration = flights[0].get('duration', 'N/A')
                return {"type": "answer", "message": f"The outbound flight duration is {duration}."}
        
        elif 'time' in message or 'depart' in message:
            if len(flights) >= 1:
                dep_time = flights[0].get('departure_date', 'N/A')
                return {"type": "answer", "message": f"The outbound flight departs at {dep_time}."}
        
        elif 'airline' in message:
            if len(flights) >= 1:
                airline = flights[0].get('airline', 'Unknown')
                return {"type": "answer", "message": f"The airline is {airline}."}
        
        elif 'cost' in message or 'price' in message:
            if len(flights) >= 1:
                cost = flights[0].get('cost', 0)
                return {"type": "answer", "message": f"The outbound flight costs ${cost:.2f}."}
    
    # Hotel questions
    elif 'hotel' in message:
        if not hotel or not isinstance(hotel, dict) or not hotel.get('name'):
            return {"type": "answer", "message": "No hotel in the current plan."}
        
        if 'name' in message:
            name = hotel.get('name', 'Unknown')
            return {"type": "answer", "message": f"The hotel is {name}."}
        
        elif 'rating' in message:
            rating = hotel.get('rating', 'N/A')
            return {"type": "answer", "message": f"The hotel rating is {rating}."}
        
        elif 'cost' in message or 'price' in message:
            cost = hotel.get('cost', 0)
            return {"type": "answer", "message": f"The hotel costs ${cost:.2f}."}
    
    # Budget questions
    elif 'budget' in message or 'cost' in message or 'total' in message:
        return {"type": "answer", "message": f"The total trip cost is ${total_cost:.2f}."}
    
    # Date questions
    elif 'date' in message or 'when' in message:
        dep = search_params.get('departure_date', 'N/A')
        ret = search_params.get('return_date', 'N/A')
        return {"type": "answer", "message": f"You depart on {dep} and return on {ret}."}
    
    # Destination questions
    elif 'where' in message or 'destination' in message:
        dest = search_params.get('destination', 'N/A')
        return {"type": "answer", "message": f"Your destination is {dest}."}
    
    # Strategy questions
    elif 'strategy' in message:
        strategy = search_params.get('strategy', 'cheapest_overall')
        strategy_display = {
            'cheapest_overall': 'Cheapest Overall',
            'splurge_flight': 'Splurge on Flights',
            'splurge_hotel': 'Splurge on Hotel'
        }.get(strategy, 'Cheapest Overall')
        return {"type": "answer", "message": f"Your current strategy is {strategy_display}."}
    
    # Help message
    elif 'help' in message or 'what can' in message:
        return {
            "type": "answer", 
            "message": "You can ask me about flights, hotels, costs, dates, or request changes like:\n" +
                      "• 'increase budget to $2000'\n" +
                      "• 'switch to splurge on flights'\n" +
                      "• 'set budget to 1800 and use cheapest overall'\n" +
                      "• 'find cheaper flights'\n" +
                      "• 'better hotels'\n" +
                      "• 'any recommendations?'"
        }
    
    # Default response
    return {
        "type": "answer",
        "message": "I'm not sure how to help with that. Try asking about flights, hotels, costs, or request changes like 'increase budget to $2000'."
    }


# ==========================================================
# CUSTOM CSS - Fresh White Theme with Vibrant Colors
# ==========================================================

st.markdown("""
<style>
    /* ===== MAIN BACKGROUND ===== */
    .stApp {
        background-color: #FFFFFF;
    }
    
    /* ===== TYPOGRAPHY ===== */
    h1, h2, h3, h4, h5, h6, p, li, span, div, label {
        color: #2D3436 !important;
    }
    
    /* ===== HEADER ===== */
    .main-header {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .main-header h1 {
        color: #FFFFFF !important;
        font-size: 2.5rem;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    .main-header p {
        color: #FFFFFF !important;
        opacity: 0.95;
        margin: 0;
    }
    
    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] {
        background-color: #F8F9FA;
        border-right: 2px solid #4ECDC4;
        padding: 1rem;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: #FF6B6B !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
        color: #FFFFFF !important;
        font-size: 0.9rem;
        padding: 0.25rem 0.5rem;
    }
    
    /* ===== EXPANDER ===== */
    .streamlit-expanderHeader {
        background-color: #F8F9FA !important;
        color: #FF6B6B !important;
        border: 2px solid #4ECDC4;
        border-radius: 10px;
        font-weight: 600;
    }
    .streamlit-expanderHeader svg {
        fill: #FF6B6B !important;
    }
    .streamlit-expanderContent {
        background-color: #F8F9FA !important;
        border: 2px solid #4ECDC4;
        border-top: none;
        border-radius: 0 0 10px 10px;
        padding: 1.5rem;
    }
    
    /* ===== INPUT FIELDS ===== */
    .stTextInput > div > div,
    .stDateInput > div > div,
    .stNumberInput > div > div,
    .stSelectbox > div > div {
        background-color: #F8F9FA !important;
        border: 2px solid #4ECDC4 !important;
        border-radius: 10px;
        transition: all 0.3s ease;
    }
    .stTextInput > div > div:hover,
    .stDateInput > div > div:hover,
    .stNumberInput > div > div:hover,
    .stSelectbox > div > div:hover {
        border-color: #FF6B6B !important;
        box-shadow: 0 4px 10px rgba(255, 107, 107, 0.1);
    }
    
    .stTextInput input,
    .stDateInput input,
    .stNumberInput input {
        color: #2D3436 !important;
        background-color: transparent !important;
        border: none !important;
        padding: 0.75rem !important;
    }
    
    .stTextInput input::placeholder,
    .stDateInput input::placeholder,
    .stNumberInput input::placeholder {
        color: #A0A0A0 !important;
    }
    
    .stTextInput label,
    .stDateInput label,
    .stNumberInput label,
    .stSelectbox label,
    .stCheckbox label {
        color: #FF6B6B !important;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    
    /* ===== DROPDOWNS ===== */
    .stSelectbox div[data-baseweb="select"] {
        background-color: #F8F9FA !important;
    }
    .stSelectbox div[data-baseweb="select"] span {
        color: #2D3436 !important;
    }
    
    div[role="listbox"] {
        background-color: #FFFFFF !important;
        border: 2px solid #4ECDC4 !important;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    div[role="listbox"] ul {
        background-color: #FFFFFF !important;
        padding: 0.5rem !important;
    }
    div[role="listbox"] li {
        color: #2D3436 !important;
        background-color: #FFFFFF !important;
        border-radius: 5px;
        padding: 0.5rem 1rem !important;
        margin: 2px 0;
    }
    div[role="listbox"] li:hover {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
    }
    
    /* ===== NUMBER INPUT BUTTONS ===== */
    .stNumberInput button {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 5px !important;
        transition: transform 0.2s ease;
    }
    .stNumberInput button:hover {
        transform: scale(1.05);
    }
    .stNumberInput button svg {
        fill: #FFFFFF !important;
    }
    
    /* ===== CALENDAR ===== */
    [data-baseweb="calendar"] {
        background-color: #FFFFFF !important;
        border: 2px solid #4ECDC4 !important;
        border-radius: 10px;
        padding: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    }
    
    [data-baseweb="calendar"] header {
        background-color: #FFFFFF !important;
        border-bottom: 2px solid #FF6B6B;
        padding-bottom: 0.5rem;
        margin-bottom: 0.5rem;
    }
    [data-baseweb="calendar"] header div {
        color: #FF6B6B !important;
        font-weight: bold;
    }
    [data-baseweb="calendar"] header button {
        background-color: #F8F9FA !important;
        color: #2D3436 !important;
        border: 2px solid #4ECDC4 !important;
        border-radius: 5px;
        transition: all 0.3s ease;
    }
    [data-baseweb="calendar"] header button:hover {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
    }
    
    [data-baseweb="calendar"] th {
        color: #4ECDC4 !important;
        background-color: #FFFFFF !important;
        padding: 0.5rem;
        font-weight: 600;
    }
    
    [data-baseweb="calendar"] td {
        background-color: #FFFFFF !important;
        padding: 0.25rem;
    }
    [data-baseweb="calendar"] button[aria-label*="day"] {
        background-color: #F8F9FA !important;
        color: #2D3436 !important;
        border: none !important;
        border-radius: 8px;
        width: 36px;
        height: 36px;
        transition: all 0.2s ease;
    }
    [data-baseweb="calendar"] button[aria-label*="day"]:hover {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
        transform: scale(1.05);
    }
    [data-baseweb="calendar"] button[aria-selected="true"] {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
        font-weight: bold;
    }
    [data-baseweb="calendar"] button[aria-label*="today"] {
        border: 2px solid #FF6B6B !important;
    }
    
    /* ===== CHECKBOX ===== */
    .stCheckbox > div > div > div {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
    }
    
    /* ===== BUTTONS ===== */
    .stButton > button {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
        color: #FFFFFF !important;
        font-weight: 600;
        border: none;
        border-radius: 25px;
        padding: 0.5rem 2rem;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 1px;
        box-shadow: 0 4px 15px rgba(255, 107, 107, 0.2);
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(78, 205, 196, 0.3);
    }
    
    /* ===== METRICS ===== */
    [data-testid="stMetricValue"] {
        color: #FF6B6B !important;
        font-size: 2rem !important;
        font-weight: bold;
    }
    [data-testid="stMetricLabel"] {
        color: #4ECDC4 !important;
        font-weight: 600;
    }
    
    /* ===== TABS ===== */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #F8F9FA;
        border-radius: 10px;
        padding: 0.5rem;
        border: 2px solid #4ECDC4;
    }
    .stTabs [data-baseweb="tab"] {
        color: #2D3436 !important;
        border: 2px solid #4ECDC4;
        border-radius: 20px;
        margin: 0 0.25rem;
        transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        border-color: #FF6B6B;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
        border-color: transparent;
    }
    
    /* ===== CHAT ===== */
    .chat-message-user {
        background: linear-gradient(135deg, #FF6B6B20, #4ECDC420);
        color: #2D3436;
        padding: 1rem;
        border-radius: 20px 20px 5px 20px;
        border: 2px solid #FF6B6B;
        margin: 0.5rem 0;
        text-align: right;
    }
    .chat-message-bot {
        background: #F8F9FA;
        color: #2D3436;
        padding: 1rem;
        border-radius: 20px 20px 20px 5px;
        border: 2px solid #4ECDC4;
        margin: 0.5rem 0;
    }
    [data-testid="stContainer"] {
        background-color: #F8F9FA !important;
        border: 2px solid #4ECDC4;
        border-radius: 10px;
        padding: 1rem;
    }
    
    /* ===== SLIDER ===== */
    .stSlider label {
        color: #FF6B6B !important;
    }
    .stSlider div[data-baseweb="slider"] {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
    }
    
    /* ===== DATAFRAME ===== */
    .dataframe {
        background-color: #FFFFFF;
        color: #2D3436;
        border: 2px solid #4ECDC4;
        border-radius: 10px;
    }
    .dataframe th {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
        color: #FFFFFF !important;
        padding: 0.75rem !important;
    }
    .dataframe td {
        background-color: #F8F9FA;
        color: #2D3436;
        padding: 0.5rem !important;
    }
    
    /* ===== ALERTS ===== */
    .stAlert {
        background-color: #F8F9FA !important;
        color: #2D3436 !important;
        border: 2px solid #FF6B6B;
        border-radius: 10px;
    }
    
    /* ===== PROGRESS BARS ===== */
    .stProgress > div > div {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4) !important;
    }
    .stProgress > div {
        background-color: #F0F0F0 !important;
    }
    
    /* ===== RADIO BUTTONS ===== */
    .stRadio > div {
        background-color: transparent !important;
    }
    .stRadio label {
        color: #2D3436 !important;
    }
    .stRadio input:checked + div {
        color: #FF6B6B !important;
    }
    
    /* ===== SPINNER ===== */
    .stSpinner > div {
        border-color: #FF6B6B transparent transparent transparent !important;
    }
    
    /* ===== FLIGHT CARDS ===== */
    .flight-card {
        background-color: #F8F9FA;
        padding: 1rem;
        border-radius: 10px;
        border: 2px solid #4ECDC4;
        margin: 0.5rem 0;
    }
    .flight-card h4 {
        color: #FF6B6B !important;
    }
    
    /* ===== HOTEL CARDS ===== */
    .hotel-card {
        background-color: #F8F9FA;
        padding: 1rem;
        border-radius: 10px;
        border: 2px solid #FF6B6B;
        margin: 0.5rem 0;
    }
    .hotel-card h4 {
        color: #4ECDC4 !important;
    }
    
    /* ===== COMMENTARY BOX ===== */
    .commentary-box {
        background: linear-gradient(135deg, #FF6B6B20, #4ECDC420);
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #FF6B6B;
        margin: 1rem 0;
        font-size: 1.1rem;
    }
    
    /* ===== PAST TRIP ITEMS ===== */
    .past-trip-item {
        background-color: #FFFFFF;
        padding: 0.75rem;
        border-radius: 8px;
        border: 1px solid #4ECDC4;
        margin: 0.5rem 0;
        transition: all 0.2s ease;
    }
    .past-trip-item:hover {
        border-color: #FF6B6B;
        box-shadow: 0 2px 8px rgba(255, 107, 107, 0.1);
    }
</style>
""", unsafe_allow_html=True)


# ==========================================================
# SESSION STATE INITIALIZATION
# ==========================================================

if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'current_result' not in st.session_state:
    st.session_state.current_result = None
if 'optimization_iterations' not in st.session_state:
    st.session_state.optimization_iterations = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'current_search_params' not in st.session_state:
    st.session_state.current_search_params = {}
if 'waiting_for_response' not in st.session_state:
    st.session_state.waiting_for_response = False
if 'show_debug' not in st.session_state:
    st.session_state.show_debug = False
if 'past_trips' not in st.session_state:
    st.session_state.past_trips = []


# ==========================================================
# HEADER
# ==========================================================

st.markdown("""
<div class="main-header">
    <h1>✈️ AI TRAVEL PLANNER</h1>
    <p>Intelligent trip optimization with chat interface</p>
</div>
""", unsafe_allow_html=True)


# ==========================================================
# PAST TRIPS SIDEBAR
# ==========================================================

with st.sidebar:
    st.markdown("### 📜 Past Trips")
    st.markdown("---")
    
    if st.session_state.past_trips:
        # Show last 10 trips in reverse chronological order
        for i, trip in enumerate(reversed(st.session_state.past_trips[-10:])):
            # Create a unique key for each trip
            trip_key = f"past_trip_{i}_{trip.get('timestamp', '')}"
            
            # Format the trip display
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"**{trip['origin']} → {trip['destination']}**")
                st.caption(f"{trip['date_range']} | ${trip['total_cost']:.0f}")
            
            with col2:
                if st.button("📋", key=f"load_{trip_key}", help="Load this trip"):
                    st.session_state.current_result = trip['result']
                    st.session_state.current_search_params = trip['search_params'].copy()
                    st.session_state.chat_history = trip.get('chat_history', []).copy()
                    st.rerun()
            
            st.markdown("---")
        
        # Clear history button
        if st.button("🗑️ Clear All History", use_container_width=True):
            st.session_state.past_trips = []
            st.rerun()
    else:
        st.info("No past trips yet. Plan your first trip!")
        st.markdown("---")
    
    # Show current session stats
    st.markdown("### 📊 Session Stats")
    if st.session_state.current_result:
        st.metric("Current Trip Cost", f"${st.session_state.current_result.get('total_cost', 0):.2f}")
    st.metric("Total Trips Planned", len(st.session_state.past_trips))
    st.metric("Chat Messages", len([m for m in st.session_state.chat_history if m['role'] == 'user']))


# ==========================================================
# MAIN CONTENT - Two columns: Main (70%) and Chat (30%)
# ==========================================================

col_main, col_chat = st.columns([0.7, 0.3])

with col_main:
    # Input section
    with st.expander("🎯 Plan a New Trip", expanded=not st.session_state.current_result):
        col1, col2 = st.columns(2)
        with col1:
            origin = st.text_input("From (City or Airport Code)", value="San Francisco", 
                                  help="Enter city name (e.g., San Francisco, New York) or airport code (e.g., SFO, JFK, LAX)")
        with col2:
            destination = st.text_input("To (City or Airport Code)", value="New York City",
                                       help="Enter city name (e.g., New York, Los Angeles) or airport code (e.g., JFK, LAX)")
        
        col3, col4 = st.columns(2)
        with col3:
            today = datetime.now().date()
            departure_date = st.date_input("Departure Date", value=today + timedelta(days=30))
        with col4:
            return_date = st.date_input("Return Date", value=today + timedelta(days=37))
        
        col5, col6 = st.columns(2)
        with col5:
            total_budget = st.number_input("Total Budget ($)", 
                                           min_value=100, max_value=10000, value=1500, step=100)
        with col6:
            # Format strategy options nicely without underscores
            strategy_options = {
                "cheapest_overall": "Cheapest Overall",
                "splurge_flight": "Splurge on Flights", 
                "splurge_hotel": "Splurge on Hotel"
            }
            selected_strategy_display = st.selectbox(
                "Budget Strategy",
                options=list(strategy_options.values()),
                index=0
            )
            # Map back to enum value
            strategy_map = {v: k for k, v in strategy_options.items()}
            strategy = strategy_map[selected_strategy_display]
        
        col7, col8 = st.columns(2)
        with col7:
            prefer_red_eyes = st.checkbox("Prefer Red-Eye Flights", value=False,
                                         help="Prefer overnight flights (usually cheaper)")
        with col8:
            adults = st.number_input("Number of Adults", min_value=1, max_value=4, value=1)
        
        # Advanced Options
        with st.expander("🔧 Advanced Options"):
            col9, col10 = st.columns(2)
            with col9:
                max_iterations = st.slider("Max Optimization Attempts", 1, 20, 3,
                                          help="Maximum number of optimization attempts (controls how many times the system tries to find a solution)")
            with col10:
                show_debug = st.checkbox("Show Debug Information", value=st.session_state.show_debug,
                                        help="Display optimization journey and API responses")
                st.session_state.show_debug = show_debug
            
            st.markdown("---")
            st.markdown(f"**Current Setting:** System will make up to **{max_iterations}** optimization attempt(s). Increase if no solution found.")
        
        if st.button("🔍 Plan My Trip", use_container_width=True):
            with st.spinner("🔄 Planning your trip... This may take a moment."):
                try:
                    # Format user input with max_iterations
                    user_input = f"""
                    Plan a trip from {origin} to {destination}.
                    Depart on {departure_date}, return on {return_date}.
                    Total budget is ${total_budget}.
                    Strategy preference: {strategy}.
                    {'Prefer red-eye flights.' if prefer_red_eyes else ''}
                    Number of adults: {adults}.
                    max_iterations: {max_iterations}
                    """
                    
                    # Store search params
                    st.session_state.current_search_params = {
                        'origin': origin,
                        'destination': destination,
                        'departure_date': departure_date,
                        'return_date': return_date,
                        'total_budget': total_budget,
                        'strategy': strategy,
                        'prefer_red_eyes': prefer_red_eyes,
                        'adults': adults,
                        'user_input': user_input,
                        'max_iterations': max_iterations,
                        'show_debug': show_debug
                    }
                    
                    # Clear previous results
                    st.session_state.optimization_iterations = []
                    st.session_state.chat_history = []
                    
                    # Run the orchestrator
                    result_str = run_overarching_bot(user_input)
                    
                    # Parse the result
                    try:
                        result_data = json.loads(result_str)
                        if isinstance(result_data, dict) and "data" in result_data:
                            result = result_data["data"]
                            formatted_message = result_data.get("formatted", "")
                            if formatted_message and not result.get("message"):
                                result["message"] = formatted_message
                            # Store optimization history
                            st.session_state.optimization_iterations = result_data.get("optimization_history", [])
                            # Store commentary
                            commentary = result_data.get("commentary", "")
                        else:
                            result = result_data
                            commentary = None
                    except json.JSONDecodeError:
                        result = {
                            "status": "complete",
                            "message": result_str,
                            "flights": [],
                            "hotel": {},
                            "total_cost": 0,
                            "remaining_budget": 0
                        }
                        commentary = None
                    
                    st.session_state.current_result = result
                    
                    # Save to past trips if we got actual results (flights exist)
                    if result and result.get('flights') and len(result.get('flights', [])) > 0:
                        date_range = f"{departure_date.strftime('%m/%d')} - {return_date.strftime('%m/%d')}"
                        trip_record = {
                            'origin': origin,
                            'destination': destination,
                            'date_range': date_range,
                            'total_cost': result.get('total_cost', 0),
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M"),
                            'result': result,
                            'search_params': st.session_state.current_search_params.copy(),
                            'chat_history': st.session_state.chat_history.copy()
                        }
                        
                        # Avoid duplicates (simple check)
                        is_duplicate = False
                        for t in st.session_state.past_trips:
                            if (t['origin'] == origin and 
                                t['destination'] == destination and 
                                abs(t['total_cost'] - result.get('total_cost', 0)) < 1):
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            st.session_state.past_trips.append(trip_record)
                    
                    # Add initial bot message to chat
                    welcome_msg = "Your trip is planned! Ask me questions or request changes like:\n"
                    welcome_msg += "• 'How long is the flight?'\n"
                    welcome_msg += "• 'Find cheaper flights'\n"
                    welcome_msg += "• 'Show me better hotels'\n"
                    welcome_msg += "• 'What's the total cost?'\n"
                    welcome_msg += "• 'Increase budget to $2000 and switch to splurge on flights'\n"
                    welcome_msg += "• 'Any recommendations?'"
                    
                    st.session_state.chat_history.append({
                        "role": "bot",
                        "message": welcome_msg
                    })
                    
                    # Add commentary to chat if available (for both success AND failure)
                    if commentary:
                        st.session_state.chat_history.append({
                            "role": "bot",
                            "message": commentary
                        })
                    
                    # Add debug info if enabled
                    if show_debug and st.session_state.optimization_iterations:
                        st.session_state.chat_history.append({
                            "role": "bot",
                            "message": f"🔧 Optimization used {len(st.session_state.optimization_iterations)} internal iterations across {max_iterations} allowed attempts."
                        })
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error planning trip: {str(e)}")
                    # Add error to chat history for visibility
                    st.session_state.chat_history.append({
                        "role": "bot",
                        "message": f"❌ An error occurred: {str(e)}"
                    })
    
    # Display current trip results
    if st.session_state.current_result:
        result = st.session_state.current_result
        
        # Check if we have any flights (success) or not (failure)
        has_flights = result.get('flights') and len(result.get('flights', [])) > 0
        
        if has_flights:
            # Success case - show metrics and details
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Cost", f"${result.get('total_cost', 0):.2f}")
            with col2:
                st.metric("Remaining Budget", f"${result.get('remaining_budget', 0):.2f}")
            with col3:
                flight_ratio = result.get('flight_ratio', 0)
                if flight_ratio:
                    st.metric("Flights %", f"{flight_ratio*100:.0f}%")
            with col4:
                hotel_ratio = result.get('hotel_ratio', 0)
                if hotel_ratio:
                    st.metric("Hotel %", f"{hotel_ratio*100:.0f}%")
            
            # Flights section
            st.markdown("### ✈️ Selected Flights")
            flights = result.get('flights', [])
            if flights:
                tabs = st.tabs([f"Flight {i+1}" for i in range(len(flights))])
                for i, (tab, flight) in enumerate(zip(tabs, flights)):
                    with tab:
                        st.markdown(f"""
                        <div class="flight-card">
                            <h4>{flight.get('airline', 'Unknown')} - {flight.get('flight_number', 'N/A')}</h4>
                            <p><strong>From:</strong> {flight.get('home_airport', 'N/A')}</p>
                            <p><strong>To:</strong> {flight.get('destination', 'N/A')}</p>
                            <p><strong>Departure:</strong> {flight.get('departure_date', 'N/A')}</p>
                            <p><strong>Arrival:</strong> {flight.get('arrival_date', 'N/A')}</p>
                            <p><strong>Duration:</strong> {flight.get('duration', 'N/A')}</p>
                            <h3 style="color: #FF6B6B;">${flight.get('cost', 0):.2f}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                
                with st.expander("📊 View Flight Comparison"):
                    flight_df = pd.DataFrame(flights)
                    display_cols = ['airline', 'flight_number', 'home_airport', 'destination', 
                                   'departure_date', 'arrival_date', 'duration', 'cost']
                    display_cols = [col for col in display_cols if col in flight_df.columns]
                    if display_cols:
                        st.dataframe(flight_df[display_cols], use_container_width=True)
            else:
                st.info("No flights found. Try adjusting your search.")
            
            # Hotel section
            st.markdown("### 🏨 Selected Hotel")
            hotel = result.get('hotel', {})
            if hotel and isinstance(hotel, dict) and hotel.get('name'):
                col1, col2 = st.columns([2, 1])
                with col1:
                    hotel_name = hotel.get('name', 'Unknown Hotel')
                    rating = hotel.get('rating', '')
                    try:
                        rating_float = float(rating) if rating else 0
                        rating_display = '⭐' * int(rating_float) if rating_float > 0 else 'Not rated'
                    except (ValueError, TypeError):
                        rating_display = 'Not rated'
                    
                    st.markdown(f"""
                    <div class="hotel-card">
                        <h4>{hotel_name}</h4>
                        <p><strong>Rating:</strong> {rating_display}</p>
                        <p><strong>Check-in:</strong> {st.session_state.current_search_params.get('departure_date', 'N/A')}</p>
                        <p><strong>Check-out:</strong> {st.session_state.current_search_params.get('return_date', 'N/A')}</p>
                        <h3 style="color: #4ECDC4;">${hotel.get('cost', 0):.2f}</h3>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown("#### Details")
                    st.write(f"**Hotel ID:** {hotel.get('hotelId', 'N/A')}")
                    st.write(f"**Offer ID:** {hotel.get('offerId', 'N/A')}")
                    st.write(f"**Currency:** {hotel.get('currency', 'USD')}")
            else:
                st.info("No hotel found. Try adjusting your search.")
        else:
            # Failure case - show helpful message
            st.markdown("""
            <div class="commentary-box">
                <strong>⚠️ No solution found within your constraints</strong>
            </div>
            """, unsafe_allow_html=True)
            
            # Show summary of what was tried
            st.markdown("### 📊 Search Summary")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Budget", f"${st.session_state.current_search_params.get('total_budget', 0):.2f}")
            with col2:
                st.metric("Attempts Used", st.session_state.current_search_params.get('max_iterations', 3))
            
            # Show flight options that were found (even if no hotel)
            flights = result.get('flights', [])
            if flights:
                st.markdown("### ✈️ Available Flights Found")
                st.info(f"Found {len(flights)} flight options starting at ${min(f.get('cost', 0) for f in flights):.2f}")
                with st.expander("View Flight Options"):
                    for i, flight in enumerate(flights):
                        st.markdown(f"""
                        <div class="flight-card">
                            <h4>{flight.get('airline', 'Unknown')} - {flight.get('flight_number', 'N/A')}</h4>
                            <p><strong>From:</strong> {flight.get('home_airport', 'N/A')}</p>
                            <p><strong>To:</strong> {flight.get('destination', 'N/A')}</p>
                            <p><strong>Departure:</strong> {flight.get('departure_date', 'N/A')}</p>
                            <p><strong>Arrival:</strong> {flight.get('arrival_date', 'N/A')}</p>
                            <p><strong>Duration:</strong> {flight.get('duration', 'N/A')}</p>
                            <h3 style="color: #FF6B6B;">${flight.get('cost', 0):.2f}</h3>
                        </div>
                        """, unsafe_allow_html=True)
            
            # Show suggestions
            st.markdown("### 💡 Suggestions")
            st.markdown("""
            - **Increase your budget** - Try adding 20-30% more or specify an amount like "increase budget to $2000"
            - **Change your strategy** - Try "switch to splurge on flights" or "use cheapest overall"
            - **Adjust your dates** - Mid-week flights are often cheaper
            - **Increase optimization attempts** - Use the slider in Advanced Options
            - **Consider different areas** - Hotels outside city center may be cheaper
            """)
        
        # Debug section - only shown when checkbox is enabled (works for both success/failure)
        if st.session_state.show_debug and st.session_state.optimization_iterations:
            with st.expander("🔧 Optimization Journey Details", expanded=False):
                st.markdown(f"**Total Internal Iterations:** {len(st.session_state.optimization_iterations)}")
                
                # Create tabs for different views of debug data
                debug_tab1, debug_tab2 = st.tabs(["📋 Summary", "🔍 Detailed JSON"])
                
                with debug_tab1:
                    # Create a summary dataframe
                    summary_data = []
                    for it in st.session_state.optimization_iterations:
                        summary_data.append({
                            "Iteration": it.get("iteration", 0),
                            "Action": it.get("action", "unknown").replace("_", " ").title(),
                            "Flight Ratio": f"{it.get('flight_ratio', 0)*100:.0f}%" if it.get('flight_ratio') else "N/A",
                            "Hotel Ratio": f"{it.get('hotel_ratio', 0)*100:.0f}%" if it.get('hotel_ratio') else "N/A",
                            "Flight Budget": f"${it.get('flight_budget', 0):.0f}" if it.get('flight_budget') else "N/A",
                            "Hotel Budget": f"${it.get('hotel_budget', 0):.0f}" if it.get('hotel_budget') else "N/A",
                            "Flights Found": it.get("valid_flights_count", 0),
                            "Hotels Found": it.get("valid_hotels_count", 0),
                            "Total Cost": f"${it.get('total_cost', 0):.0f}" if it.get("total_cost") else "N/A"
                        })
                    
                    if summary_data:
                        st.dataframe(pd.DataFrame(summary_data), use_container_width=True)
                    
                    # Show message if available
                    for it in st.session_state.optimization_iterations:
                        if it.get("message"):
                            st.info(f"**Iteration {it.get('iteration')}:** {it.get('message')}")
                
                with debug_tab2:
                    # Show raw JSON for each iteration
                    for i, it in enumerate(st.session_state.optimization_iterations):
                        with st.expander(f"Iteration {it.get('iteration', i+1)} Details"):
                            st.json(it)

with col_chat:
    # Chat interface
    st.markdown("### 💬 Chat with Your Travel Planner")
    
    # Display chat history in a scrollable container
    chat_container = st.container(height=450)
    with chat_container:
        if st.session_state.chat_history:
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    st.markdown(f'<div class="chat-message-user">👤 {msg["message"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="chat-message-bot">🤖 {msg["message"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color: #CCCCCC; text-align: center; padding: 2rem;">👈 Plan a trip to start chatting!</div>', unsafe_allow_html=True)
    
    # Chat input
    if st.session_state.current_result:
        user_message = st.chat_input("Ask me anything about your trip...")
        
        if user_message and not st.session_state.waiting_for_response:
            # Add user message to chat
            st.session_state.chat_history.append({"role": "user", "message": user_message})
            st.session_state.waiting_for_response = True
            
            # Process the message
            with st.spinner("🤔 Thinking..."):
                response = process_chat_message(
                    user_message, 
                    st.session_state.current_result,
                    st.session_state.current_search_params
                )
                
                # Check if this is a recommendation request
                if response.get("type") == "recommendation":
                    st.session_state.chat_history.append({
                        "role": "bot", 
                        "message": f"💡 {response['message']}"
                    })
                    
                    if response.get("action"):
                        # Update search params based on recommendation
                        if response['action'] == 'search_hotels':
                            st.session_state.chat_history.append({
                                "role": "bot",
                                "message": "I've found some hotel options. Please use the 'Plan a New Trip' button above with adjusted preferences to see them, or ask me to 'find cheaper flights' instead."
                            })
                        elif response['action'] == 'search_flights':
                            st.session_state.chat_history.append({
                                "role": "bot",
                                "message": "I've found some flight options. Please use the 'Plan a New Trip' button above with adjusted preferences to see them, or ask me to 'find better hotels' instead."
                            })
                        elif response['action'] == 'adjust_budget':
                            st.session_state.current_search_params['total_budget'] = response['params']['new_budget']
                            # Update user_input with new budget
                            old_input = st.session_state.current_search_params['user_input']
                            budget_match = re.search(r'\$\d+', old_input)
                            if budget_match:
                                st.session_state.current_search_params['user_input'] = old_input.replace(
                                    budget_match.group(), 
                                    f'${int(response["params"]["new_budget"])}'
                                )
                            st.session_state.chat_history.append({
                                "role": "bot",
                                "message": f"Budget updated to ${response['params']['new_budget']:.0f}. Click 'Plan My Trip' again to search with the new budget!"
                            })
                
                # Check if this is a modification request
                elif response.get("type") == "modification":
                    # Show modification message
                    st.session_state.chat_history.append({
                        "role": "bot", 
                        "message": response['message']
                    })
                    
                    # Update search params - can handle multiple changes at once
                    params_updated = False
                    
                    # Update budget if specified
                    if "budget" in response and response['budget'] is not None:
                        st.session_state.current_search_params['total_budget'] = response['budget']
                        # Update user_input with new budget
                        old_input = st.session_state.current_search_params['user_input']
                        budget_match = re.search(r'\$\d+', old_input)
                        if budget_match:
                            st.session_state.current_search_params['user_input'] = old_input.replace(
                                budget_match.group(), 
                                f'${int(response["budget"])}'
                            )
                        params_updated = True
                    
                    # Update strategy if specified
                    if "strategy" in response and response['strategy'] is not None:
                        st.session_state.current_search_params['strategy'] = response['strategy']
                        # Update user_input with new strategy
                        old_input = st.session_state.current_search_params['user_input']
                        # Replace the strategy line in user_input
                        st.session_state.current_search_params['user_input'] = re.sub(
                            r'Strategy preference:.*?\n',
                            f'Strategy preference: {response["strategy"]}.\n',
                            old_input
                        )
                        params_updated = True
                    
                    # Update preference if specified
                    if "preference" in response and response['preference'] is not None:
                        st.session_state.current_search_params['prefer_red_eyes'] = response['preference']
                        # Update user_input with new preference
                        old_input = st.session_state.current_search_params['user_input']
                        if "Prefer red-eye flights." in old_input:
                            if not response['preference']:
                                st.session_state.current_search_params['user_input'] = old_input.replace(
                                    "Prefer red-eye flights.", ""
                                )
                        else:
                            if response['preference']:
                                st.session_state.current_search_params['user_input'] = old_input + " Prefer red-eye flights."
                        params_updated = True
                    
                    if params_updated:
                        # Re-run the orchestrator with updated params
                        new_result_str = run_overarching_bot(st.session_state.current_search_params['user_input'])
                        try:
                            new_result_data = json.loads(new_result_str)
                            if isinstance(new_result_data, dict) and "data" in new_result_data:
                                st.session_state.current_result = new_result_data["data"]
                                # Update optimization history
                                st.session_state.optimization_iterations = new_result_data.get("optimization_history", [])
                                # Get new commentary
                                new_commentary = new_result_data.get("commentary", "")
                            else:
                                st.session_state.current_result = new_result_data
                                new_commentary = None
                            
                            # Save this updated trip to past trips if flights found
                            if st.session_state.current_result and st.session_state.current_result.get('flights') and len(st.session_state.current_result.get('flights', [])) > 0:
                                params = st.session_state.current_search_params
                                date_range = f"{params['departure_date'].strftime('%m/%d')} - {params['return_date'].strftime('%m/%d')}"
                                trip_record = {
                                    'origin': params['origin'],
                                    'destination': params['destination'],
                                    'date_range': date_range,
                                    'total_cost': st.session_state.current_result.get('total_cost', 0),
                                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    'result': st.session_state.current_result,
                                    'search_params': params.copy(),
                                    'chat_history': st.session_state.chat_history.copy()
                                }
                                st.session_state.past_trips.append(trip_record)
                            
                            st.session_state.chat_history.append({
                                "role": "bot",
                                "message": "✅ I've updated your trip plan! Check the new options above."
                            })
                            
                            # Add new commentary if available
                            if new_commentary:
                                st.session_state.chat_history.append({
                                    "role": "bot",
                                    "message": new_commentary
                                })
                            
                            # Add debug info if enabled
                            if st.session_state.show_debug and st.session_state.optimization_iterations:
                                st.session_state.chat_history.append({
                                    "role": "bot",
                                    "message": f"🔧 Re-optimization used {len(st.session_state.optimization_iterations)} internal iterations."
                                })
                                
                        except Exception as e:
                            st.session_state.chat_history.append({
                                "role": "bot",
                                "message": f"❌ Sorry, I couldn't update the plan: {str(e)}"
                            })
                    
                else:
                    # Regular Q&A response
                    st.session_state.chat_history.append({
                        "role": "bot", 
                        "message": response["message"]
                    })
                
                st.session_state.waiting_for_response = False
                st.rerun()


# ==========================================================
# FOOTER
# ==========================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #FF6B6B; padding: 1rem;">
    <p>Powered by Amadeus API and OpenAI | © 2026 SJSU CMPE 297 Group 3 - AI Travel Planner</p>
    <p style="font-size: 0.8rem;">Optimization attempts controlled by slider in Advanced Options (default: 3, max: 20)</p>
</div>
""", unsafe_allow_html=True)