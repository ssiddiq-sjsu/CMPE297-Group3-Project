"""
Streamlit GUI for Travel Planner - Hybrid Architecture with Natural Events
- Deterministic optimization backend
- LLM-powered conversational frontend
- Events panel with pure LLM responses
"""

import streamlit as st
from datetime import datetime, timedelta
import json
import os
import re
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Import orchestrator
from overarching_bot import plan_trip, Strategy, parse_user_input
from airline_codes import get_airline_with_code, resolve_airline_code
from weather import get_weather_forecast
from events_bot import search_events

# Initialize OpenAI client
client = OpenAI(timeout=30.0)

# Constants
MAX_CHAT_HISTORY = 50
API_TIMEOUT = 30
RATE_LIMIT_SECONDS = 2

# Page config
st.set_page_config(
    page_title="AI Travel Planner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================================
# CUSTOM CSS
# ==========================================================
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
        padding: 2rem;
        border-radius: 15px;
        margin-bottom: 2rem;
        text-align: center;
    }
    .main-header h1 {
        color: #FFFFFF !important;
    }
    .chat-message-user {
        background: linear-gradient(135deg, #FF6B6B20, #4ECDC420);
        padding: 1rem;
        border-radius: 20px 20px 5px 20px;
        border: 2px solid #FF6B6B;
        margin: 0.5rem 0;
        text-align: right;
    }
    .chat-message-bot {
        background: #F8F9FA;
        padding: 1rem;
        border-radius: 20px 20px 20px 5px;
        border: 2px solid #4ECDC4;
        margin: 0.5rem 0;
    }
    .weather-card {
        background: linear-gradient(135deg, #4ECDC4, #45B7AA);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        color: white;
    }
    .red-eye-badge {
        background-color: #FF6B6B;
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 20px;
        font-size: 0.8rem;
        display: inline-block;
    }
    .events-container {
    max-height: 400px;
    overflow-y: auto;
    padding: 10px;
    background: #f8f9fa;
    border-radius: 10px;
    margin: 10px 0;
    border: 1px solid #4ECDC4;
    }
    .event-day {
        margin-bottom: 15px;
        padding: 10px;
        background: white;
        border-radius: 8px;
        border-left: 3px solid #4ECDC4;
    }
    .event-item {
        padding: 5px 0;
        border-bottom: 1px solid #eee;
        font-size: 0.9rem;
    }
    .event-item:last-child {
        border-bottom: none;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================================
# CHAT FUNCTION SCHEMAS
# ==========================================================

CHAT_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Search for new flight options",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Origin city or airport code"},
                    "destination": {"type": "string", "description": "Destination city or airport code"},
                    "departure_date": {"type": "string", "description": "Departure date (YYYY-MM-DD)"},
                    "return_date": {"type": "string", "description": "Return date (YYYY-MM-DD)"}
                },
                "required": ["origin", "destination", "departure_date", "return_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search for new hotel options",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "Destination city or area"},
                    "check_in": {"type": "string", "description": "Check-in date (YYYY-MM-DD)"},
                    "check_out": {"type": "string", "description": "Check-out date (YYYY-MM-DD)"}
                },
                "required": ["destination", "check_in", "check_out"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_budget",
            "description": "Change the trip budget",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_budget": {"type": "number", "description": "New budget amount in USD"}
                },
                "required": ["new_budget"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "change_strategy",
            "description": "Change the budget allocation strategy",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_strategy": {
                        "type": "string",
                        "enum": ["cheapest_overall", "splurge_flight", "splurge_hotel"],
                        "description": "New strategy to use"
                    }
                },
                "required": ["new_strategy"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_iterations",
            "description": "Change the number of optimization iterations",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_iterations": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Number of optimization attempts"
                    }
                },
                "required": ["new_iterations"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_dates",
            "description": "Change travel dates",
            "parameters": {
                "type": "object",
                "properties": {
                    "departure_date": {"type": "string", "description": "New departure date (YYYY-MM-DD)"},
                    "return_date": {"type": "string", "description": "New return date (YYYY-MM-DD)"}
                },
                "required": ["departure_date", "return_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_preferences",
            "description": "Update travel preferences like red-eye flights",
            "parameters": {
                "type": "object",
                "properties": {
                    "prefer_red_eyes": {
                        "type": "boolean",
                        "description": "Whether to prefer red-eye flights (overnight flights between 9PM-5AM)"
                    }
                },
                "required": ["prefer_red_eyes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_better_hotel",
            "description": "Find a better hotel than the current one (higher rated or different option)",
            "parameters": {
                "type": "object",
                "properties": {
                    "preference": {
                        "type": "string",
                        "enum": ["higher_rated", "different", "any"],
                        "description": "What kind of better hotel to look for"
                    }
                },
                "required": ["preference"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Search for local events, concerts, festivals, sports, food events, or things to do during your trip",
            "parameters": {
                "type": "object",
                "properties": {
                    "preferences": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "What kind of events? Examples: ['music'], ['sports', 'food'], ['family', 'outdoor'], ['concerts', 'festivals']",
                    }
                },
                "required": [],
            },
        }
    }  
]


def execute_functions(function_calls: list, current_params: dict, trip_result: dict) -> dict:
    """Execute multiple function calls and return updates."""
    all_updates = {}
    all_results = []
    should_replan = False
    find_better = False
    current_hotel = None
    
    for func_call in function_calls:
        function_name = func_call["function"]
        arguments = func_call["arguments"]
        
        if function_name == "adjust_budget":
            new_budget = arguments.get("new_budget")
            if new_budget:
                all_updates["total_budget"] = float(new_budget)
                all_results.append(f"BUDGET_CHANGED:${new_budget}")
                should_replan = True
        
        elif function_name == "change_strategy":
            new_strategy = arguments.get("new_strategy")
            if new_strategy:
                all_updates["strategy"] = new_strategy
                strategy_display = {
                    'cheapest_overall': 'Cheapest Overall',
                    'splurge_flight': 'Splurge on Flights',
                    'splurge_hotel': 'Splurge on Hotel'
                }.get(new_strategy, new_strategy)
                all_results.append(f"STRATEGY_CHANGED:{strategy_display}")
                should_replan = True
        
        elif function_name == "adjust_iterations":
            new_iterations = arguments.get("new_iterations")
            if new_iterations:
                all_updates["max_iterations"] = int(new_iterations)
                all_results.append(f"ITERATIONS_CHANGED:{new_iterations}")
                should_replan = True
        
        elif function_name == "update_dates":
            departure = arguments.get("departure_date")
            return_date = arguments.get("return_date")
            if departure:
                all_updates["departure_date"] = departure
            if return_date:
                all_updates["return_date"] = return_date
            all_results.append(f"DATES_CHANGED:{departure} to {return_date}")
            should_replan = True
        
        elif function_name == "update_preferences":
            prefer_red_eyes = arguments.get("prefer_red_eyes")
            if prefer_red_eyes is not None:
                all_updates["prefer_red_eyes"] = prefer_red_eyes
                status = "enabled" if prefer_red_eyes else "disabled"
                all_results.append(f"REDEYE_{status.upper()}")
                should_replan = True
        
        elif function_name == "find_better_hotel":
            preference = arguments.get("preference", "any")
            find_better = True
            current_hotel = trip_result.get("data", {}).get("hotel", {})
            current_rating = current_hotel.get("rating", "Unknown")
            all_results.append(f"FIND_BETTER_HOTEL: current rating {current_rating}⭐")
            all_updates["find_better_hotel"] = True
            should_replan = True
        
        elif function_name == "search_events":
            preferences = arguments.get("preferences", [])
            
            # Search for events (returns raw data only)
            events_result = search_events(
                destination=st.session_state.current_params['destination'],
                start_date=st.session_state.current_params['departure_date'],
                end_date=st.session_state.current_params['return_date'],
                preferences=preferences,
                exclude_ids=st.session_state.excluded_event_ids,
                max_events=8,
            )
            
            # Store events for panel display
            if events_result["has_events"]:
                st.session_state.current_events = events_result["panel_html"]
                st.session_state.current_events_data = events_result
                st.session_state.excluded_event_ids = events_result["event_ids"]
            
            # Return RAW DATA - LLM will generate response
            all_results.append(json.dumps(events_result))
            should_replan = False
        
        elif function_name in ["search_flights", "search_hotels"]:
            should_replan = True
            all_results.append(f"SEARCH_NEW_{function_name.upper()}")
    
    return {
        "updates": all_updates,
        "results": all_results,
        "should_replan": should_replan,
        "find_better": find_better,
        "current_hotel": current_hotel
    }


def get_conversational_response(user_message: str, trip_data: dict, chat_history: list, function_results: list = None) -> str:
    """Get a natural language response from the LLM."""
    
    # Build rich context
    flights = trip_data.get("data", {}).get("flights", [])
    hotel = trip_data.get("data", {}).get("hotel", {})
    metadata = trip_data.get("metadata", {})
    
    # Format flight information nicely
    flight_info = []
    red_eye_count = 0
    for i, f in enumerate(flights, 1):
        direction = "Outbound" if i == 1 else "Return"
        airline = f.get('airline', 'Unknown')
        airline_code = f.get('airline_code', '')
        if airline_code and airline != airline_code:
            airline_display = f"{airline} ({airline_code})"
        else:
            airline_display = airline
        
        # Check if red-eye
        dep = f.get('departure_date', '')
        is_red_eye = False
        if " " in dep:
            try:
                t = datetime.strptime(dep.split(" ")[1][:5], "%H:%M")
                hour = t.hour + t.minute / 60
                is_red_eye = hour >= 21 or hour < 5
                if is_red_eye:
                    red_eye_count += 1
            except:
                pass
        
        red_eye_marker = " 🌙" if is_red_eye else ""
        
        flight_info.append(f"{direction} Flight{red_eye_marker}: {airline_display} {f.get('flight_number', '')}")
        flight_info.append(f"  • Depart: {f.get('departure_date', 'Unknown')}")
        flight_info.append(f"  • Arrive: {f.get('arrival_date', 'Unknown')}")
        flight_info.append(f"  • Duration: {f.get('duration', 'Unknown')}")
        flight_info.append(f"  • Cost: ${f.get('cost', 0):.2f}")
    
    # Format hotel information
    hotel_info = []
    if hotel:
        hotel_info.append(f"Hotel: {hotel.get('name', 'Unknown')}")
        hotel_info.append(f"  • Total Cost: ${hotel.get('total', 0):.2f}")
        if hotel.get('rating'):
            hotel_info.append(f"  • Rating: {hotel.get('rating')}⭐")
    else:
        hotel_info.append("No hotel selected yet.")
    
    # Add weather if available
    weather_info = None
    if 'weather_cache' in st.session_state:
        dest = metadata.get('destination', '')
        weather_info = st.session_state.weather_cache.get(dest)
    
    # Parse any event data from function results
    event_data = None
    if function_results:
        for result in function_results:
            try:
                # Try to parse as JSON (event data)
                parsed = json.loads(result)
                if isinstance(parsed, dict) and "has_events" in parsed:
                    event_data = parsed
                    break
            except:
                pass
    
    context = {
        "current_trip": {
            "origin": metadata.get("origin", "Unknown"),
            "destination": metadata.get("destination", "Unknown"),
            "dates": f"{metadata.get('departure_date')} to {metadata.get('return_date')}",
            "total_budget": f"${metadata.get('total_budget', 0):.2f}",
            "total_cost": f"${trip_data.get('data', {}).get('total_cost', 0):.2f}",
            "remaining_budget": f"${trip_data.get('data', {}).get('remaining_budget', 0):.2f}",
            "strategy": metadata.get('strategy', 'cheapest_overall').replace('_', ' ').title(),
            "optimization_status": trip_data.get('data', {}).get('status', 'unknown'),
            "iterations_used": f"{trip_data.get('data', {}).get('iterations_used', 0)}/{metadata.get('max_iterations', 5)}",
            "red_eye_enabled": metadata.get('prefer_red_eyes', False),
            "red_eye_flights_found": red_eye_count,
            "weather": weather_info,
            "recommended_events": [
                (e.get("title") or "Event") + (f" ({(e.get('start') or '')[:10]})" if e.get("start") else "")
                for e in trip_data.get('data', {}).get('recommended_events', [])
            ]
        },
        "flights": "\n".join(flight_info) if flight_info else "No flights found.",
        "hotel": "\n".join(hotel_info) if hotel_info else "No hotel found.",
        "events": event_data  # Add event data to context
    }
    
    system_prompt = f"""You are a friendly and knowledgeable travel assistant. Your role is to help users plan their trip by having natural conversations.

CURRENT TRIP CONTEXT:
{json.dumps(context, indent=2)}

WEATHER INFORMATION:
{json.dumps(weather_info, indent=2) if weather_info else "No weather data available"}

RECENT FUNCTION RESULTS (including event data if any):
{json.dumps(function_results, indent=2) if function_results else "No recent changes"}

You have access to these functions:
- search_flights: Find new flight options
- search_hotels: Find new hotel options
- adjust_budget: Change total budget
- change_strategy: Change allocation strategy
- adjust_iterations: Change optimization attempts
- update_dates: Change travel dates
- update_preferences: Enable/disable red-eye flights
- find_better_hotel: Find higher rated or different hotel
- search_events: Find local events during your trip

Guidelines for your responses:
1. Be conversational and friendly - use emojis appropriately
2. When users ask questions, provide helpful answers using the context
3. If they ask for something you don't have, explain what you can do instead
4. After making changes, explain what happened in a natural way
5. Keep responses concise but warm - 2-3 sentences usually
6. If they're asking about flight times, reference the specific flights
7. If weather info is available, mention it when relevant
8. If red-eye is enabled and flights found, mention you found overnight options
9. If no red-eye flights available, suggest they try different dates
10. When finding better hotels:
    - If UPGRADE_SUCCESS: Be excited! Mention the rating improvement and ask what you can help with next.
    - If FOUND_ALTERNATIVE: Mention you found another option with same rating to stay within budget
    - If NO_BETTER_HOTEL: Explain no better options found and suggest increasing budget
    - Don't just say "searching" - respond to what actually happened which already presented to the user.
    
11. WHEN YOU SEARCH FOR EVENTS:
    - You'll receive data about what was found. Use this to craft natural responses.

    IF EVENTS WERE FOUND:
    - Mention the total number of events found
    - Highlight 1-2 interesting events (title, day, category)
    - Reference that they can see all events in the panel above
    - Ask if they want more like a specific type or different categories

    Example tone (NOT hardcoded - just examples):
    - "Great news! I found 8 events in New York! There's a Knicks game on Wednesday and Hamilton on Thursday - both look amazing! Check out the panel above for all the details. Want me to find more concerts like the jazz one?"
    - "Found 4 food events during your stay! The Taste of NYC festival on Tuesday has 100+ vendors. Take a look at the panel - any of these catch your eye?"
    - "I searched for music events and found 6 shows! The Blue Note has jazz on Friday night that's really popular. Want to see more options or try a different category?"

    IF NO EVENTS FOUND:
    - Be helpful and suggest trying different preferences or dates
    - Example: "I couldn't find any events matching '{{preferences}}' in {destination}. Want to try different dates or maybe explore food festivals instead?"

    IF USER ASKS FOR "MORE LIKE THAT":
    - They want similar events (same category)
    - You can call search_events again with refined preferences

    IF USER ASKS FOR "DIFFERENT" EVENTS:
    - They want different categories than what they saw
    - Call search_events with new preferences

    WHEN DATES OR FLIGHTS OR HOTELS CHANGE:
    - If user previously asked for events, ASK if they want to search again 
    - Example: "I've updated your dates. Would you like me to search for events during your new stay dates?"
    - Do NOT assume they want events automatically

Remember: You're helping a real person plan their vacation. Be excited for them! Be enthusiastic, reference the panel, and always offer next steps naturally!"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m["role"], "content": m["message"]} for m in chat_history[-8:]],
    ]
    
    messages.append({"role": "user", "content": user_message})
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
            timeout=10
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"I'm having trouble responding right now. Error: {str(e)}"


def process_chat_message(user_message: str, trip_data: dict, chat_history: list, current_params: dict) -> dict:
    """Process chat message - determine if function calls are needed."""
    
    # Build context for function calling
    context = {
        "current_trip": {
            "origin": trip_data.get("metadata", {}).get("origin", "Unknown"),
            "destination": trip_data.get("metadata", {}).get("destination", "Unknown"),
            "departure_date": trip_data.get("metadata", {}).get("departure_date"),
            "return_date": trip_data.get("metadata", {}).get("return_date"),
            "total_budget": trip_data.get("metadata", {}).get("total_budget", 0),
            "strategy": trip_data.get("metadata", {}).get("strategy", "cheapest_overall"),
            "total_cost": trip_data.get("data", {}).get("total_cost", 0),
            "iterations_used": trip_data.get("data", {}).get("iterations_used", 0),
            "max_iterations": trip_data.get("metadata", {}).get("max_iterations", 5),
            "prefer_red_eyes": current_params.get("prefer_red_eyes", False)
        }
    }
    
    system_prompt = f"""You are a travel assistant that helps users by calling functions when they want to make changes.

Current trip context:
{json.dumps(context, indent=2)}

Available functions:
- search_flights: When user wants to search for new flights
- search_hotels: When user wants to search for new hotels  
- adjust_budget: When user wants to change budget
- change_strategy: When user wants to change allocation strategy
- adjust_iterations: When user wants to change optimization iterations
- update_dates: When user wants to change travel dates
- update_preferences: When user wants to enable/disable red-eye flights
- find_better_hotel: When user says 'find better hotel', 'better hotel', 'upgrade hotel'
- search_events: When user wants to find local events, things to do, concerts, etc.

If the user is just asking a question or having a conversation, do NOT call any functions.
Only call functions when they explicitly want to make changes to the trip, search for events, or update their preferences.
You can call multiple functions if the user makes multiple requests in one message."""

    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m["role"], "content": m["message"]} for m in chat_history[-5:]],
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            tools=CHAT_FUNCTIONS,
            tool_choice="auto",
            max_tokens=200,
            temperature=0.0,
            timeout=10
        )
        
        message = response.choices[0].message
        
        if message.tool_calls and len(message.tool_calls) > 0:
            # Extract function calls
            function_calls = []
            for tool_call in message.tool_calls:
                function_calls.append({
                    "function": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments)
                })
            
            return {
                "type": "function_calls",
                "function_calls": function_calls
            }
        else:
            return {
                "type": "conversation",
                "function_calls": []
            }
            
    except Exception as e:
        print(f"Error in process_chat_message: {e}")
        return {
            "type": "conversation",
            "function_calls": []
        }


# ==========================================================
# SESSION STATE
# ==========================================================

if 'trip_result' not in st.session_state:
    st.session_state.trip_result = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'optimization_iterations' not in st.session_state:
    st.session_state.optimization_iterations = []
if 'weather_cache' not in st.session_state:
    st.session_state.weather_cache = {}
if 'current_events' not in st.session_state:
    st.session_state.current_events = None
if 'current_events_data' not in st.session_state:
    st.session_state.current_events_data = None
if 'excluded_event_ids' not in st.session_state:
    st.session_state.excluded_event_ids = []
if 'current_params' not in st.session_state:
    st.session_state.current_params = {
        'origin': 'San Francisco',
        'destination': 'New York City',
        'departure_date': (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        'return_date': (datetime.now() + timedelta(days=37)).strftime("%Y-%m-%d"),
        'total_budget': 1500.0,
        'strategy': 'cheapest_overall',
        'prefer_red_eyes': False,
        'adults': 1,
        'max_iterations': 5,
    }
if 'last_chat_time' not in st.session_state:
    st.session_state.last_chat_time = 0
if 'show_debug' not in st.session_state:
    st.session_state.show_debug = False
if 'processing_message' not in st.session_state:
    st.session_state.processing_message = False


# ==========================================================
# UI HEADER
# ==========================================================

st.markdown("""
<div class="main-header">
    <h1>✈️ AI TRAVEL PLANNER</h1>
    <p>Your Personal AI Travel Assistant ✈️ Flights 🏨 Hotels 🎉 Events 🌤️ Weather 💬 Chat</p>
</div>
""", unsafe_allow_html=True)


# ==========================================================
# SIDEBAR - Trip Parameters
# ==========================================================

with st.sidebar:
    st.markdown("### 🎯 Your Trip Details")
    
    origin = st.text_input("From", value=st.session_state.current_params['origin'])
    destination = st.text_input("To", value=st.session_state.current_params['destination'])
    
    col1, col2 = st.columns(2)
    with col1:
        departure = st.date_input(
            "Depart",
            value=datetime.strptime(st.session_state.current_params['departure_date'], "%Y-%m-%d").date()
        )
    with col2:
        return_date = st.date_input(
            "Return",
            value=datetime.strptime(st.session_state.current_params['return_date'], "%Y-%m-%d").date()
        )
    
    if return_date <= departure:
        st.error("Return date must be after departure date!")
        valid_dates = False
    else:
        valid_dates = True
        nights = (return_date - departure).days
        st.caption(f"📅 {nights} nights")
    
    total_budget = st.number_input(
        "Budget ($)",
        min_value=100.0,
        max_value=10000.0,
        value=float(st.session_state.current_params['total_budget']),
        step=100.0
    )
    
    strategy_options = {
        "cheapest_overall": "Cheapest Overall",
        "splurge_flight": "Splurge on Flights",
        "splurge_hotel": "Splurge on Hotel"
    }
    current_strategy = st.session_state.current_params['strategy']
    strategy = st.selectbox(
        "Strategy",
        options=list(strategy_options.keys()),
        format_func=lambda x: strategy_options[x],
        index=list(strategy_options.keys()).index(current_strategy) if current_strategy in strategy_options else 0
    )
    
    col3, col4 = st.columns(2)
    with col3:
        prefer_red_eyes = st.checkbox(
            "🌙 Prefer Red-Eye",
            value=st.session_state.current_params['prefer_red_eyes']
        )
        if prefer_red_eyes != st.session_state.current_params['prefer_red_eyes']:
            st.session_state.current_params['prefer_red_eyes'] = prefer_red_eyes
            st.rerun()
    with col4:
        adults = st.number_input(
            "Adults",
            min_value=1,
            max_value=4,
            value=st.session_state.current_params['adults']
        )
    
    max_iterations = st.slider(
        "Optimization Attempts",
        min_value=1,
        max_value=20,
        value=st.session_state.current_params['max_iterations']
    )
    
    show_debug = st.checkbox("🔧 Show Debug Info", value=st.session_state.show_debug)
    st.session_state.show_debug = show_debug
    
    if st.button("🔍 Plan New Trip", use_container_width=True, disabled=not valid_dates):
        st.session_state.current_params.update({
            'origin': origin,
            'destination': destination,
            'departure_date': departure.strftime("%Y-%m-%d"),
            'return_date': return_date.strftime("%Y-%m-%d"),
            'total_budget': float(total_budget),
            'strategy': strategy,
            'prefer_red_eyes': prefer_red_eyes,
            'adults': adults,
            'max_iterations': max_iterations,
        })
        
        # Clear events when planning new trip
        st.session_state.current_events = None
        st.session_state.current_events_data = None
        st.session_state.excluded_event_ids = []
        
        with st.spinner("Planning your perfect trip..."):
            try:
                result = plan_trip(
                    origin=origin,
                    destination=destination,
                    departure_date=departure.strftime("%Y-%m-%d"),
                    return_date=return_date.strftime("%Y-%m-%d"),
                    total_budget=float(total_budget),
                    strategy=Strategy(strategy),
                    prefer_red_eyes=prefer_red_eyes,
                    adults=adults,
                    max_iterations=max_iterations,
                )
                
                st.session_state.trip_result = result
                st.session_state.optimization_iterations = result.get("optimization_history", [])
                
                # Clear old weather and fetch new
                st.session_state.weather_cache = {}
                
                # Get a warm welcome with trip context
                trip_context = f"I just planned a trip from {origin} to {destination} from {departure.strftime('%B %d')} to {return_date.strftime('%B %d')} with a budget of ${total_budget}. Can you welcome me and help me with my trip?"

                welcome_message = get_conversational_response(
                    trip_context,
                    result,
                    [],
                    None
                )
                st.session_state.chat_history = [{"role": "assistant", "message": welcome_message}]
                
                st.rerun()
                
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    st.markdown("---")
    if st.session_state.trip_result:
        total = st.session_state.trip_result.get("data", {}).get("total_cost", 0)
        st.metric("Current Total", f"${total:.2f}")


# ==========================================================
# MAIN CONTENT - Results and Chat
# ==========================================================

col_main, col_chat = st.columns([0.7, 0.3])

with col_main:
    if st.session_state.trip_result:
        result = st.session_state.trip_result
        data = result.get("data", {})
        metadata = result.get("metadata", {})
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Cost", f"${data.get('total_cost', 0):.2f}")
        with col2:
            remaining = float(data.get('remaining_budget', 0) or 0)
            if remaining < 0:
                st.markdown(
                    '<div style="background-color: rgba(49, 51, 63, 0.6); padding: 1rem 1rem 1rem 1rem; '
                    'border-radius: 0.5rem; border: 1px solid rgba(250, 250, 250, 0.2);">'
                    '<p style="color: rgba(250, 250, 250, 0.6); font-size: 0.875rem; margin: 0 0 0.25rem 0;">Remaining</p>'
                    f'<p style="color: #ff4b4b; font-size: 1.5rem; font-weight: 600; margin: 0;" '
                    f'title="You are over budget">${remaining:.2f}</p>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.metric("Remaining", f"${remaining:.2f}")
        with col3:
            if data.get('flight_ratio'):
                st.metric("Flights %", f"{data['flight_ratio']*100:.0f}%")
            else:
                iterations_used = data.get("iterations_used", 0)
                max_iterations = metadata.get("max_iterations", 5)
                st.metric("Iterations", f"{iterations_used}/{max_iterations}")
        with col4:
            if data.get('hotel_ratio'):
                st.metric("Hotel %", f"{data['hotel_ratio']*100:.0f}%")
            else:
                status = data.get("status", "unknown")
                st.metric("Status", status.replace("_", " ").title())
        
        # Red-eye indicator
        if metadata.get('prefer_red_eyes', False):
            st.markdown('<span class="red-eye-badge">🌙 Red-eye mode enabled</span>', unsafe_allow_html=True)
        
        # Flights
        st.markdown("### ✈️ Your Flights")
        flights = data.get('flights', [])
        if flights:
            red_eye_count = 0
            for i, flight in enumerate(flights, 1):
                airline = flight.get('airline', 'Unknown')
                airline_code = flight.get('airline_code', '')
                flight_num = flight.get('flight_number', '')
                dep = flight.get('departure_date', '')
                
                # Check if red-eye
                is_red_eye = False
                if " " in dep:
                    try:
                        t = datetime.strptime(dep.split(" ")[1][:5], "%H:%M")
                        hour = t.hour + t.minute / 60
                        is_red_eye = hour >= 21 or hour < 5
                        if is_red_eye:
                            red_eye_count += 1
                    except:
                        pass
                
                if airline_code and airline != airline_code:
                    airline_display = f"{airline} ({airline_code})"
                else:
                    airline_display = airline
                
                red_eye_badge = " 🌙" if is_red_eye else ""
                
                with st.container():
                    cols = st.columns([2, 1, 1, 1])
                    with cols[0]:
                        st.markdown(f"**{airline_display}{red_eye_badge}**")
                        st.caption(f"{flight_num} • {flight.get('home_airport')} → {flight.get('destination')}")
                    with cols[1]:
                        st.markdown(f"Depart\n{flight.get('departure_date', 'N/A')}")
                    with cols[2]:
                        st.markdown(f"Arrive\n{flight.get('arrival_date', 'N/A')}")
                    with cols[3]:
                        st.markdown(f"**${flight.get('cost', 0):.2f}**")
                    st.divider()
            
            if metadata.get('prefer_red_eyes', False) and red_eye_count == 0:
                st.warning("No red-eye flights available for this route. Try different dates!")
        else:
            st.info("No flights found for this route")
        
        # Hotel
        st.markdown("### 🏨 Your Hotel")
        hotel = data.get('hotel')
        if hotel:
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.markdown(f"**{hotel.get('name', 'Unknown')}**")
                rating = hotel.get('rating')
                if rating:
                    st.caption(f"Rating: {rating}⭐")
            with cols[1]:
                st.markdown("Total")
            with cols[2]:
                st.markdown(f"**${hotel.get('total', 0):.2f}**")
        else:
            st.info("No hotel found")

        # Recommended events (one per day)
        st.markdown("### 🎉 Recommended Events")
        recommended_events = data.get("recommended_events") or []
        if recommended_events:
            for i, ev in enumerate(recommended_events, 1):
                title = ev.get("title") or "Event"
                start_raw = ev.get("start") or ""
                category = (ev.get("category") or "").replace("-", " ").title()
                try:
                    if start_raw:
                        dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                        start_str = dt.strftime("%a, %b %d at %I:%M %p")
                    else:
                        start_str = ""
                except (ValueError, TypeError):
                    start_str = start_raw[:16] if start_raw else ""
                with st.container():
                    st.markdown(f"**Day {i}:** {title}")
                    if start_str:
                        st.caption(f"📅 {start_str}")
                    if category:
                        st.caption(f"🏷️ {category}")
                    st.divider()
        else:
            st.caption("No events found for your trip dates. Try another destination or date range.")

        # Weather
        if hotel or flights:
            st.markdown("### 🌤️ Destination Weather")
            with st.spinner("Checking forecast..."):
                dest_city = metadata.get('destination', 'New York City')
                arrival_date = metadata.get('departure_date')
                
                city_for_weather = dest_city.split(',')[0].strip()
                
                if dest_city not in st.session_state.weather_cache:
                    weather = get_weather_forecast(city_for_weather, arrival_date)
                    if weather:
                        st.session_state.weather_cache[dest_city] = weather
                else:
                    weather = st.session_state.weather_cache[dest_city]
                
                if weather:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Temperature", f"{weather['temperature']}°F", 
                                 help="Forecast for arrival day")
                    with col2:
                        st.metric("Conditions", f"{weather['emoji']} {weather['description']}")
                    with col3:
                        st.metric("Wind", f"{weather['wind']} mph")
                    
                    if weather.get('humidity'):
                        st.caption(f"Humidity: {weather['humidity']}%")
                else:
                    st.caption("🌡️ Weather forecast unavailable")
        
        # Debug section
        if st.session_state.show_debug:
            with st.expander("🔧 Optimization Details"):
                iterations_used = data.get("iterations_used", 0)
                max_iterations = metadata.get("max_iterations", 0)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Iterations Used", f"{iterations_used}/{max_iterations}")
                with col2:
                    status = data.get("status", "unknown")
                    st.metric("Status", status.replace("_", " ").title())
                
                history = result.get("optimization_history", [])
                if history:
                    st.write(f"**Optimization Steps:**")
                    for i, it in enumerate(history):
                        st.json(it)
    else:
        st.info("👈 Enter your trip details and click 'Plan New Trip' to get started!")

with col_chat:
    st.markdown("### 💬 Chat with Your Assistant")
    
    chat_container = st.container(height=500)
    with chat_container:
        if st.session_state.chat_history:
            for msg in st.session_state.chat_history:
                if msg["role"] == "user":
                    st.markdown(f'<div class="chat-message-user">👤 {msg["message"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="chat-message-bot">🤖 {msg["message"]}</div>', unsafe_allow_html=True)
        else:
            st.caption("Plan a trip first, then chat with me!")
    
    if st.session_state.trip_result and not st.session_state.processing_message:
        user_message = st.chat_input("Ask me anything about your trip...")
        
        current_time = time.time()
        if user_message and (current_time - st.session_state.last_chat_time) >= RATE_LIMIT_SECONDS:
            st.session_state.last_chat_time = current_time
            st.session_state.processing_message = True
            
            # Add user message immediately
            st.session_state.chat_history.append({"role": "user", "message": user_message})
            
            with st.spinner("🤔 Thinking..."):
                # Step 1: Determine if function calls are needed
                process_result = process_chat_message(
                    user_message,
                    st.session_state.trip_result,
                    st.session_state.chat_history[:-1],
                    st.session_state.current_params
                )
                
                function_results = None
                should_replan = False
                find_better = False
                current_hotel_data = None
                
                # Step 2: Execute any function calls
                if process_result["type"] == "function_calls" and process_result["function_calls"]:
                    exec_result = execute_functions(
                        process_result["function_calls"],
                        st.session_state.current_params,
                        st.session_state.trip_result
                    )
                    
                    function_results = exec_result.get("results", [])
                    find_better = exec_result.get("find_better", False)
                    current_hotel_data = exec_result.get("current_hotel")
                    
                    # Update params
                    if exec_result["updates"]:
                        for key, value in exec_result["updates"].items():
                            st.session_state.current_params[key] = value
                        should_replan = True
                
                # Step 3: Replan if needed
                if should_replan:
                    with st.spinner("🔄 Updating your trip..."):
                        try:
                            new_result = plan_trip(
                                origin=st.session_state.current_params['origin'],
                                destination=st.session_state.current_params['destination'],
                                departure_date=st.session_state.current_params['departure_date'],
                                return_date=st.session_state.current_params['return_date'],
                                total_budget=float(st.session_state.current_params['total_budget']),
                                strategy=Strategy(st.session_state.current_params['strategy']),
                                prefer_red_eyes=st.session_state.current_params['prefer_red_eyes'],
                                adults=st.session_state.current_params['adults'],
                                max_iterations=st.session_state.current_params['max_iterations'],
                                find_better_hotel=find_better,
                                current_hotel=current_hotel_data if find_better else None
                            )
                            
                            # Enhance function results with upgrade information
                            if find_better and current_hotel_data:
                                new_hotel = new_result.get("data", {}).get("hotel", {})
                                if new_hotel and new_hotel.get("hotelId") != current_hotel_data.get("hotelId"):
                                    old_rating = current_hotel_data.get("rating", "Unknown")
                                    new_rating = new_hotel.get("rating", "Unknown")
                                    
                                    try:
                                        old_int = int(float(old_rating)) if old_rating else 0
                                        new_int = int(float(new_rating)) if new_rating else 0
                                    except:
                                        old_int = 0
                                        new_int = 0
                                    
                                    if new_int > old_int:
                                        function_results.append(f"UPGRADE_SUCCESS: Found a {new_rating}⭐ hotel (was {old_rating}⭐)")
                                    elif new_int == old_int:
                                        function_results.append(f"FOUND_ALTERNATIVE: Found another {new_rating}⭐ hotel")
                                    else:
                                        function_results.append("FOUND_OPTION: Found a different hotel")
                                else:
                                    function_results.append("NO_BETTER_HOTEL: Could not find better hotel within budget")
                            
                            st.session_state.trip_result = new_result
                            st.session_state.optimization_iterations = new_result.get("optimization_history", [])
                            
                            # Clear weather cache for new search
                            if 'weather_cache' in st.session_state:
                                st.session_state.weather_cache = {}
                                
                        except Exception as e:
                            function_results = [f"Error updating: {str(e)}"]
                            print(f"Replan error: {e}")
                
                # Step 4: Get natural language response (LLM handles everything)
                response = get_conversational_response(
                    user_message,
                    st.session_state.trip_result,
                    st.session_state.chat_history[:-1],
                    function_results
                )
                
                st.session_state.chat_history.append({"role": "assistant", "message": response})
                
                # Trim history
                if len(st.session_state.chat_history) > MAX_CHAT_HISTORY:
                    st.session_state.chat_history = st.session_state.chat_history[-MAX_CHAT_HISTORY:]
            
            st.session_state.processing_message = False
            st.rerun()
        
        elif user_message:
            wait_time = RATE_LIMIT_SECONDS - (current_time - st.session_state.last_chat_time)
            if wait_time > 0:
                st.warning(f"Please wait {wait_time:.1f}s")


# ==========================================================
# FOOTER
# ==========================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>Your Personal AI Travel Assistant | Powered by Amadeus, OpenAI, OpenWeatherMap & PredictHQ</p>
</div>
""", unsafe_allow_html=True)