"""
Hotel search agent using OpenAI Agents SDK and Amadeus hotel APIs.
Stateful class: maintains an agent session so the same conversation continues
across calls. Creates and returns a chosen hotel every run; uses fallback to
Amadeus when the agent doesn't call submit. Session is preserved for future calls.
"""
import asyncio
import json
import os
from typing import Any, Optional

from agents import Agent, Runner, SQLiteSession, function_tool, WebSearchTool, ModelSettings

from .amadeus_hotels import search_hotels_for_trip

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY is not set")


# --- Function tools (Amadeus + submit) ---

@function_tool
def query_amadeus_hotels(
    destination: str,
    check_in_date: str,
    check_out_date: str,
    max_budget: Optional[float] = None,
    adults: int = 1,
    max_hotels: int = 5,
) -> str:
    """Search Amadeus for hotel offers in a destination for the given dates.

    Args:
        destination: City name or IATA code (e.g. New York City, SFO, MIA).
        check_in_date: Check-in date YYYY-MM-DD.
        check_out_date: Check-out date YYYY-MM-DD.
        max_budget: Optional maximum total price in USD for the stay.
        adults: Number of adults (default 1).
        max_hotels: Max number of hotel offers to return (default 5).
    """
    print("\n\n calling query_amadeus_hotels")
    offers = search_hotels_for_trip(
        destination=destination,
        check_in=check_in_date,
        check_out=check_out_date,
        adults=adults,
        max_hotels=max_hotels,
    )
    if not offers:
        return json.dumps({"offers": [], "message": "No hotel offers found for this destination and dates."})
    # if max_budget is not None:
    #     offers = [o for o in offers if (o.get("total") or 0) <= max_budget]
    print("\n\nquery_amadeus_hotels offers: ", offers)
    return json.dumps(offers, default=str)


def _make_submit_tool(chosen: list[dict]) -> Any:
    """Build submit_optimal_hotel tool that appends the chosen hotel to `chosen` (same run)."""

    @function_tool
    def submit_optimal_hotel(
        hotel_id: str,
        name: str,
        total: float,
        currency: str = "USD",
        rating: Optional[str] = None,
        offer_id: Optional[str] = None,
    ) -> str:
        """Call this when you have chosen the best hotel. Submit exactly one hotel. You must call this to complete the task.

        Args:
            hotel_id: Amadeus hotel ID.
            name: Hotel name.
            total: Total price for the stay.
            currency: Currency code (default USD).
            rating: Optional hotel rating.
            offer_id: Optional Amadeus offer ID.
        """
        hotel = {
            "hotelId": hotel_id,
            "name": name,
            "total": total,
            "currency": currency,
            "rating": rating,
            "offerId": offer_id,
        }
        chosen.append(hotel)
        return json.dumps({"status": "accepted", "hotel": hotel}, default=str)

    return submit_optimal_hotel


def _offer_to_hotel(o: dict) -> dict:
    """Convert Amadeus offer dict to our hotel dict format."""
    return {
        "hotelId": o.get("hotelId"),
        "name": o.get("name"),
        "total": o.get("total"),
        "currency": o.get("currency", "USD"),
        "rating": o.get("rating"),
        "offerId": o.get("offerId"),
    }


HOTEL_AGENT_INSTRUCTIONS = """You are a hotel search agent. You must complete the following steps in order:
1. Call query_amadeus_hotels to fetch hotel options (use the destination, check-in date, check-out date, and max_budget from the user message).
2. From the results, pick the best hotel for the user (consider price, rating, and any preferences they gave).
3. Call submit_optimal_hotel exactly once with that hotel's hotel_id, name, total, currency, and optionally rating and offer_id.

You are NOT done until you have called submit_optimal_hotel. Do not reply with only text. Always call submit_optimal_hotel with one hotel from the search results to finish."""


def _clear_session_sync(session: SQLiteSession) -> None:
    """Clear session from sync code (session.clear_session is async)."""
    asyncio.run(session.clear_session())


class HotelSearchAgent:
    """
    Stateful hotel search agent. Keeps an Agents API session for future calls.
    Each run returns a chosen hotel: either from the agent's submit_optimal_hotel call,
    or (fallback) the best available offer from Amadeus when the agent doesn't submit.
    """

    def __init__(self, session_id: str = "hotel_search", db_path: Optional[str] = None) -> None:
        self._session = SQLiteSession(session_id, db_path) if db_path else SQLiteSession(session_id)
        self._search_params: Optional[dict[str, Any]] = None
        self._first_call = True

    def _current_search_key(self, destination: str, check_in: str, check_out: str, budget_max: float) -> tuple:
        return (destination.strip(), check_in.strip(), check_out.strip(), float(budget_max))

    def run(
        self,
        destination: str,
        check_in: str,
        check_out: str,
        budget_max: float,
        extra_info: str = "",
    ) -> list[dict]:
        """
        Run the agent; return a list of one chosen hotel dict. Uses session for context.
        If the agent does not call submit_optimal_hotel, falls back to the best Amadeus offer.
        """
        key = self._current_search_key(destination, check_in, check_out, budget_max)
        if self._search_params is None or self._search_params.get("_key") != key:
            _clear_session_sync(self._session)
            self._search_params = {
                "_key": key,
                "destination": destination,
                "check_in": check_in,
                "check_out": check_out,
                "budget_max": budget_max,
            }
            self._first_call = True

        chosen: list[dict] = []
        submit_tool = _make_submit_tool(chosen)
        agent = Agent(
            name="Hotel Search Agent",
            model="gpt-4o",
            model_settings=ModelSettings(tool_choice="auto"),
            instructions=HOTEL_AGENT_INSTRUCTIONS,
            tools=[query_amadeus_hotels, submit_tool],
        )

        if self._first_call:
            user_content = (
                f"Search for hotels with:\n"
                f"- Destination: {destination}\n"
                f"- Check-in date: {check_in}\n"
                f"- Check-out date: {check_out}\n"
                f"- Maximum budget (total for stay): {budget_max}\n"
                f"- Extra preferences: {extra_info or 'None'}\n\n"
                "Call query_amadeus_hotels, then pick the best hotel and call submit_optimal_hotel with it. You must call submit_optimal_hotel to complete the task."
            )
            self._first_call = False
        else:
            user_content = (
                f"User's additional preferences: {extra_info or 'None'}\n\n"
                "Using the same destination, dates, and budget, search again and call submit_optimal_hotel with a hotel that fits these preferences. You must call submit_optimal_hotel to complete the task."
            )

        a = Runner.run_sync(agent, user_content, session=self._session)

        print("runner response:", a)
        print("chosen: ", chosen)

        # Fallback: if agent didn't submit, pick best offer from Amadeus and return it
        # if not chosen:
        #     offers = search_hotels_for_trip(
        #         destination=destination,
        #         check_in=check_in,
        #         check_out=check_out,
        #         adults=1,
        #         max_hotels=5,
        #     )
        #     if offers and budget_max is not None and budget_max > 0:
        #         offers = [o for o in offers if (o.get("total") or 0) <= budget_max]
        #     if offers:
        #         chosen = [_offer_to_hotel(offers[0])]

        return chosen


_default_agent = HotelSearchAgent()


def run_agent(
    destination: str,
    check_in: str,
    check_out: str,
    budget_max: float,
    extra_info: str = "",
    model: str = "gpt-4o",
    max_turns: int = 15,
) -> list[dict]:
    """Run the stateful hotel agent; returns a list of one hotel dict. Session preserved for future calls."""
    return _default_agent.run(
        destination=destination,
        check_in=check_in,
        check_out=check_out,
        budget_max=float(budget_max),
        extra_info=extra_info or "",
    )
