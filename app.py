"""
Streamlit GUI for Travel Orchestrator

This provides a user-friendly interface for the travel planning system.
Users can input trip details, preferences, and see optimized results.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import os
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

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background-color: #f0f2f6;
    }
    .main-header {
        color: #1e3c72;
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .main-header h1 {
        color: white;
        margin: 0;
    }
    .main-header p {
        color: #e0e0e0;
        margin: 0;
    }
    .success-box {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #17a2b8;
        margin: 1rem 0;
    }
    .flight-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        border-left: 4px solid #667eea;
    }
    .hotel-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        border-left: 4px solid #764ba2;
    }
    .metric-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 25px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'search_history' not in st.session_state:
    st.session_state.search_history = []
if 'current_result' not in st.session_state:
    st.session_state.current_result = None
if 'optimization_iterations' not in st.session_state:
    st.session_state.optimization_iterations = []

# Header
st.markdown("""
<div class="main-header">
    <h1>✈️ AI Travel Planner</h1>
    <p>Intelligent trip optimization using Amadeus API and OpenAI</p>
</div>
""", unsafe_allow_html=True)

# Sidebar for inputs
with st.sidebar:
    st.markdown("### 🎯 Trip Details")
    
    # Trip basics
    origin = st.text_input("From (Airport Code)", value="SFO", 
                          help="Enter airport code (e.g., SFO, JFK, LAX)")
    
    destination = st.text_input("To (City or Airport Code)", value="New York City",
                               help="Enter city name or airport code")
    
    col1, col2 = st.columns(2)
    with col1:
        today = datetime.now().date()
        departure_date = st.date_input("Departure", value=today + timedelta(days=30))
    with col2:
        return_date = st.date_input("Return", value=today + timedelta(days=37))
    
    # Budget
    st.markdown("### 💰 Budget")
    total_budget = st.number_input("Total Trip Budget ($)", 
                                   min_value=100, max_value=10000, value=1500, step=100)
    
    # Preferences
    st.markdown("### ⚙️ Preferences")
    
    strategy = st.selectbox(
        "Budget Strategy",
        options=[s.value for s in Strategy],
        index=0,
        help="Choose how to allocate budget between flights and hotels"
    )
    
    prefer_red_eyes = st.checkbox("Prefer Red-Eye Flights", value=False,
                                  help="Prefer overnight flights (usually cheaper)")
    
    adults = st.number_input("Number of Adults", min_value=1, max_value=4, value=1)
    
    # Advanced options
    with st.expander("Advanced Options"):
        max_iterations = st.slider("Max Optimization Iterations", 1, 20, 10)
        show_debug = st.checkbox("Show Debug Information", value=False)
    
    # Search button
    search_button = st.button("🔍 Plan My Trip", type="primary", use_container_width=True)
    
    # History
    if st.session_state.search_history:
        st.markdown("### 📜 Recent Searches")
        for i, search in enumerate(st.session_state.search_history[-5:]):
            if st.button(f"{search['origin']} → {search['destination']}", key=f"hist_{i}"):
                st.session_state.current_result = search['result']

# Main content area
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="metric-card">
        <h3>✈️ Flights</h3>
        <p style="font-size: 0.9rem; color: #666;">70/30 split for splurge</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="metric-card">
        <h3>🏨 Hotels</h3>
        <p style="font-size: 0.9rem; color: #666;">40/60 split for splurge</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="metric-card">
        <h3>⚖️ Strategy</h3>
        <p style="font-size: 0.9rem; color: #666;">{}</p>
    </div>
    """.format(strategy), unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="metric-card">
        <h3>💰 Budget</h3>
        <p style="font-size: 0.9rem; color: #666;">${}</p>
    </div>
    """.format(total_budget), unsafe_allow_html=True)

# Process search
if search_button:
    with st.spinner("🔄 Planning your trip... This may take a moment."):
        try:
            # Format user input for the orchestrator
            user_input = f"""
            Plan a trip from {origin} to {destination}.
            Depart on {departure_date}, return on {return_date}.
            Total budget is ${total_budget}.
            Strategy preference: {strategy}.
            {'Prefer red-eye flights.' if prefer_red_eyes else ''}
            Number of adults: {adults}.
            """
            
            # Clear previous iterations
            st.session_state.optimization_iterations = []
            
            # Run the orchestrator
            result_str = run_overarching_bot(user_input)
            
            # Parse the result - it could be a JSON string or formatted text
            try:
                # Try to parse as JSON first
                result_data = json.loads(result_str)
                
                # Check if it's our new format with data field
                if isinstance(result_data, dict) and "data" in result_data:
                    result = result_data["data"]
                    formatted_message = result_data.get("formatted", "")
                    # Store the formatted message for display
                    if formatted_message and not result.get("message"):
                        result["message"] = formatted_message
                else:
                    # Old format - just the data
                    result = result_data
            except json.JSONDecodeError:
                # If not JSON, it's just a text response
                result = {
                    "status": "complete",
                    "message": result_str,
                    "flights": [],
                    "hotel": {},
                    "total_cost": 0,
                    "remaining_budget": 0,
                    "flight_ratio": None,
                    "hotel_ratio": None
                }
            
            # Store in session state
            st.session_state.current_result = result
            st.session_state.search_history.append({
                'origin': origin,
                'destination': destination,
                'result': result,
                'timestamp': datetime.now()
            })
            
        except Exception as e:
            st.error(f"Error planning trip: {str(e)}")
            if show_debug:
                st.exception(e)

# Display results
if st.session_state.current_result:
    result = st.session_state.current_result
    
    # If result has a message field, show it
    if result.get("message") and not result.get("flights"):
        st.markdown(f"""
        <div class="success-box">
            <h3>✅ Trip Planned Successfully!</h3>
            <p>{result['message']}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("---")
        
        # Success message
        st.markdown("""
        <div class="success-box">
            <h3>✅ Trip Planned Successfully!</h3>
            <p>Your optimized itinerary is ready below.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total = result.get('total_cost', 0)
            st.metric("Total Cost", f"${total:.2f}")
        
        with col2:
            remaining = result.get('remaining_budget', 0)
            st.metric("Remaining Budget", f"${remaining:.2f}")
        
        with col3:
            flight_ratio = result.get('flight_ratio', 0)
            if flight_ratio:
                st.metric("Flight %", f"{flight_ratio*100:.0f}%")
        
        with col4:
            hotel_ratio = result.get('hotel_ratio', 0)
            if hotel_ratio:
                st.metric("Hotel %", f"{hotel_ratio*100:.0f}%")
        
        # Flights section
        st.markdown("### ✈️ Selected Flights")
        
        flights = result.get('flights', [])
        if flights and len(flights) > 0:
            tabs = st.tabs([f"Flight {i+1}" for i in range(len(flights))])
            
            for i, (tab, flight) in enumerate(zip(tabs, flights)):
                with tab:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"""
                        <div class="flight-card">
                            <h4>{flight.get('airline', 'Unknown')} - {flight.get('flight_number', 'N/A')}</h4>
                            <p><strong>From:</strong> {flight.get('home_airport', 'N/A')}</p>
                            <p><strong>To:</strong> {flight.get('destination', 'N/A')}</p>
                            <p><strong>Departure:</strong> {flight.get('departure_date', 'N/A')}</p>
                            <p><strong>Arrival:</strong> {flight.get('arrival_date', 'N/A')}</p>
                            <p><strong>Duration:</strong> {flight.get('duration', 'N/A')}</p>
                            <h3 style="color: #667eea;">${flight.get('cost', 0):.2f}</h3>
                        </div>
                        """, unsafe_allow_html=True)
            
            # Flight comparison table
            with st.expander("View Flight Comparison"):
                flight_df = pd.DataFrame(flights)
                display_cols = ['airline', 'flight_number', 'home_airport', 'destination', 
                               'departure_date', 'arrival_date', 'duration', 'cost']
                # Only show columns that exist
                display_cols = [col for col in display_cols if col in flight_df.columns]
                if display_cols:
                    st.dataframe(flight_df[display_cols], use_container_width=True)
        else:
            st.info("No flights were found matching your criteria. Try adjusting your budget or dates.")
        
        # Hotel section
        st.markdown("### 🏨 Selected Hotel")
        
        hotel = result.get('hotel', {})
        if hotel and hotel.get('name'):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Get hotel name safely
                hotel_name = hotel.get('name', 'Unknown Hotel')
                if not hotel_name and 'hotelId' in hotel:
                    hotel_name = f"Hotel {hotel.get('hotelId', '')}"
                
                # Get rating safely
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
                    <p><strong>Location:</strong> {destination}</p>
                    <p><strong>Check-in:</strong> {departure_date}</p>
                    <p><strong>Check-out:</strong> {return_date}</p>
                    <h3 style="color: #764ba2;">${hotel.get('cost', 0):.2f}</h3>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                # Hotel details
                st.markdown("#### Details")
                st.write(f"**Hotel ID:** {hotel.get('hotelId', 'N/A')}")
                st.write(f"**Offer ID:** {hotel.get('offerId', 'N/A')}")
                st.write(f"**Currency:** {hotel.get('currency', 'USD')}")
        else:
            st.info("No hotels were found matching your criteria. Try adjusting your budget or dates.")
        
        # Optimization journey (debug info)
        if show_debug and st.session_state.optimization_iterations:
            with st.expander("🔧 Optimization Journey"):
                for i, iteration in enumerate(st.session_state.optimization_iterations):
                    st.markdown(f"**Iteration {i+1}:**")
                    st.json(iteration)
        
        # Action buttons
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📥 Download Itinerary", use_container_width=True):
                # Create itinerary text
                itinerary = f"""
                TRAVEL ITINERARY
                ================
                
                Trip: {origin} → {destination}
                Dates: {departure_date} to {return_date}
                Total Cost: ${result.get('total_cost', 0):.2f}
                Remaining Budget: ${result.get('remaining_budget', 0):.2f}
                
                FLIGHTS:
                """
                
                for i, flight in enumerate(flights, 1):
                    itinerary += f"""
                Flight {i}: {flight.get('airline', 'Unknown')} {flight.get('flight_number', '')}
                    {flight.get('home_airport', '')} → {flight.get('destination', '')}
                    Depart: {flight.get('departure_date', '')}
                    Arrive: {flight.get('arrival_date', '')}
                    Duration: {flight.get('duration', '')}
                    Cost: ${flight.get('cost', 0):.2f}
                """
                
                hotel_name = hotel.get('name', 'Unknown Hotel') if hotel else 'None'
                hotel_cost = hotel.get('cost', 0) if hotel else 0
                
                itinerary += f"""
                
                HOTEL:
                {hotel_name}
                Cost: ${hotel_cost:.2f}
                """
                
                st.download_button(
                    label="📄 Download as Text",
                    data=itinerary,
                    file_name=f"itinerary_{origin}_{destination}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        
        with col2:
            if st.button("🔄 New Search", use_container_width=True):
                st.session_state.current_result = None
                st.rerun()
        
        with col3:
            if st.button("📧 Email Itinerary", use_container_width=True):
                st.info("Email functionality coming soon!")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>Powered by Amadeus API and OpenAI | © 2024 AI Travel Planner</p>
</div>
""", unsafe_allow_html=True)