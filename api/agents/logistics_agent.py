"""
Logistics Agent with Microsoft Agent Framework

This module defines the logistics agent configuration, tools, and state schema
for the shipping logistics demo backed by v2 Responses API.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Annotated

from agent_framework import ChatAgent, ChatClientProtocol, ai_function
from agent_framework_ag_ui import AgentFrameworkAgent
from agent_framework_ag_ui._orchestrators import HumanInTheLoopOrchestrator
from pydantic import Field

from middleware import DeduplicatingOrchestrator


# Load flight data from JSON file
_DATA_FILE = Path(__file__).parent.parent / "data" / "flights.json"

def _load_flight_data() -> dict:
    """Load flight data from the JSON file."""
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Module-level cache for flight data
_FLIGHT_DATA: dict = {}

def _get_flight_data() -> dict:
    """Get cached flight data, loading if necessary."""
    if not _FLIGHT_DATA:
        _FLIGHT_DATA.update(_load_flight_data())
    return _FLIGHT_DATA

def _get_all_flights() -> list[dict]:
    """Get all flights from the data file."""
    return _get_flight_data().get("flights", [])

def _get_historical_data() -> list[dict]:
    """Get historical data from the data file."""
    return _get_flight_data().get("historicalData", [])


# State schema for the logistics agent
STATE_SCHEMA: dict[str, object] = {
    "flights": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "flightNumber": {"type": "string"},
                "flightDate": {"type": "string"},
                "from": {"type": "string"},
                "to": {"type": "string"},
                "currentPounds": {"type": "number"},
                "maxPounds": {"type": "number"},
                "currentCubicFeet": {"type": "number"},
                "maxCubicFeet": {"type": "number"},
                "utilizationPercent": {"type": "number"},
                "riskLevel": {"type": "string"},
                "sortTime": {"type": "string"},
            },
        },
        "description": "List of flight shipments to display in the dashboard.",
    },
    "selectedFlight": {
        "type": "object",
        "description": "The currently selected flight for detailed view.",
    },
    "historicalData": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "pounds": {"type": "number"},
                "cubicFeet": {"type": "number"},
                "predicted": {"type": "boolean"},
            },
        },
        "description": "Historical and predicted payload data for charts.",
    },
    "selectedRoute": {
        "type": "string",
        "description": "The currently selected or filtered route (e.g., 'LAX → ORD').",
    },
    "activeFilter": {
        "type": "object",
        "properties": {
            "route": {"type": "string"},
            "utilizationType": {"type": "string", "enum": ["all", "over", "under"]},
        },
        "description": "Active filter for the flight list (route and/or utilization type).",
    },
    "viewMode": {
        "type": "string",
        "enum": ["list", "detail", "chart"],
        "description": "Current view mode of the dashboard.",
    },
    "highlightRisks": {
        "type": "boolean",
        "description": "Whether to highlight risk flights with colors.",
    },
    "maxFlights": {
        "type": "number",
        "description": "Maximum number of flights to display in the dashboard (5, 10, 15, or 20).",
    },
}

PREDICT_STATE_CONFIG: dict[str, dict[str, str]] = {
    # Map update tools to state - these tools' arguments are extracted and used to update UI state
    "flights": {
        "tool": "update_flights",
        "tool_argument": "flights",
    },
    "selectedFlight": {
        "tool": "update_selected_flight",
        "tool_argument": "flight",
    },
    "historicalData": {
        "tool": "update_historical_data",
        "tool_argument": "historical_data",
    },
}


# Tool definitions
@ai_function(
    name="update_flights",
    description="Update the flight list displayed in the dashboard.",
)
def update_flights(
    flights: Annotated[
        list[dict],
        Field(description="The list of flights to display in the dashboard."),
    ],
) -> str:
    """Update the flights displayed in the dashboard."""
    return f"Dashboard updated with {len(flights)} flights."


@ai_function(
    name="update_selected_flight",
    description="Set the selected flight to show detailed information.",
)
def update_selected_flight(
    flight: Annotated[
        dict | None,
        Field(description="The flight to select and show details for, or null to clear selection."),
    ],
) -> str:
    """Update the selected flight in the dashboard."""
    if flight:
        return f"Showing details for flight {flight.get('flightNumber', 'unknown')}."
    return "Flight selection cleared."


@ai_function(
    name="update_historical_data",
    description="Update the historical payload chart data.",
)
def update_historical_data(
    historical_data: Annotated[
        list[dict],
        Field(description="Historical and predicted payload data points."),
    ],
) -> str:
    """Update the historical chart data."""
    predicted_count = sum(1 for d in historical_data if d.get("predicted", False))
    historical_count = len(historical_data) - predicted_count
    return f"Chart updated with {historical_count} historical and {predicted_count} predicted data points."


@ai_function(
    name="get_over_utilized_flights",
    description="Get the top N over-utilized flights (utilization > 85%) for the next sort time. This updates the dashboard display automatically.",
)
def get_over_utilized_flights(
    count: Annotated[
        int,
        Field(description="Number of flights to return.", default=10),
    ] = 10,
) -> dict:
    """Retrieve over-utilized flights and return structured data for state update."""
    all_flights = _get_all_flights()
    # Filter for over-utilized flights (high or critical risk level)
    over_utilized = [f for f in all_flights if f.get("riskLevel") in ["high", "critical"]]
    flights = over_utilized[:count]
    return {
        "message": f"Found {len(flights)} over-utilized flights. The dashboard has been updated.",
        "flights": flights,
    }


@ai_function(
    name="get_under_utilized_flights",
    description="Get the top N under-utilized flights (utilization < 50%) for the next sort time. This updates the dashboard display automatically.",
)
def get_under_utilized_flights(
    count: Annotated[
        int,
        Field(description="Number of flights to return.", default=10),
    ] = 10,
) -> dict:
    """Retrieve under-utilized flights and return structured data for state update."""
    all_flights = _get_all_flights()
    # Filter for under-utilized flights (low risk level)
    under_utilized = [f for f in all_flights if f.get("riskLevel") == "low"]
    flights = under_utilized[:count]
    return {
        "message": f"Found {len(flights)} under-utilized flights. The dashboard has been updated.",
        "flights": flights,
    }


@ai_function(
    name="get_optimal_flights",
    description="Get flights with optimal utilization (50-80% capacity). These are well-balanced flights that don't need adjustment. This updates the dashboard display automatically.",
)
def get_optimal_flights(
    count: Annotated[
        int,
        Field(description="Number of flights to return.", default=10),
    ] = 10,
) -> dict:
    """Retrieve optimally-utilized flights and return structured data for state update."""
    all_flights = _get_all_flights()
    # Filter for optimal flights (medium risk level = 50-80% utilization)
    optimal = [f for f in all_flights if f.get("riskLevel") == "medium"]
    flights = optimal[:count]
    return {
        "message": f"Found {len(flights)} optimally-utilized flights (50-80% capacity). The dashboard has been updated.",
        "flights": flights,
    }


@ai_function(
    name="get_predicted_payload",
    description="Get predicted payload data for upcoming flights. This updates the dashboard display automatically.",
)
def get_predicted_payload(
    count: Annotated[
        int,
        Field(description="Number of flights to return.", default=10),
    ] = 10,
) -> dict:
    """Retrieve predicted payload for upcoming flights and return structured data."""
    all_flights = _get_all_flights()
    # Return a mix of flights for predicted payload view
    flights = all_flights[:count]
    return {
        "message": f"Predicted payload for {len(flights)} upcoming flights. The dashboard has been updated.",
        "flights": flights,
    }


@ai_function(
    name="get_flight_details",
    description="Get detailed payload information for a specific flight by flight number. This updates the dashboard to show the flight detail card.",
)
def get_flight_details(
    flight_number: Annotated[
        str,
        Field(description="The flight number to look up (e.g., 'LAX-ORD-2847')."),
    ],
) -> dict:
    """Retrieve detailed information for a specific flight and return structured data."""
    all_flights = _get_all_flights()
    
    # Normalize flight number for matching
    search_number = flight_number.upper().replace(" ", "")
    
    # Find the flight by flight number
    for flight in all_flights:
        if flight.get("flightNumber", "").upper() == search_number:
            return {
                "message": f"Showing details for flight {flight['flightNumber']}.",
                "selectedFlight": flight,
            }
    
    # If not found, return the first flight with matching route pattern
    parts = search_number.split("-")
    if len(parts) >= 2:
        from_code = parts[0]
        to_code = parts[1]
        for flight in all_flights:
            if flight.get("from") == from_code and flight.get("to") == to_code:
                return {
                    "message": f"Showing details for flight {flight['flightNumber']} (closest match).",
                    "selectedFlight": flight,
                }
    
    # Return first flight as fallback
    if all_flights:
        return {
            "message": f"Flight {flight_number} not found. Showing {all_flights[0]['flightNumber']} instead.",
            "selectedFlight": all_flights[0],
        }
    
    return {
        "message": "No flights available.",
        "selectedFlight": None,
    }


@ai_function(
    name="get_utilization_risks",
    description="Get all flights with utilization risk (either over or under utilized). This updates the dashboard display automatically.",
)
def get_utilization_risks(
    count: Annotated[
        int,
        Field(description="Number of risk flights to return.", default=15),
    ] = 15,
) -> dict:
    """Retrieve flights with utilization risks and return structured data."""
    all_flights = _get_all_flights()
    # Filter for flights with risk (not medium utilization)
    risk_flights = [f for f in all_flights if f.get("riskLevel") != "medium"]
    flights = risk_flights[:count]
    
    over = [f for f in flights if f["riskLevel"] in ["high", "critical"]]
    under = [f for f in flights if f["riskLevel"] == "low"]
    
    return {
        "message": f"Found {len(flights)} flights with utilization risks: {len(over)} over-utilized, {len(under)} under-utilized. The dashboard has been updated.",
        "flights": flights,
    }


@ai_function(
    name="get_historical_payload",
    description="Get historical payload data and predictions for trend analysis. This updates the dashboard chart.",
)
def get_historical_payload(
    days: Annotated[
        int,
        Field(description="Number of historical days to retrieve.", default=7),
    ] = 7,
    include_predictions: Annotated[
        int,
        Field(description="Number of prediction days to include.", default=3),
    ] = 3,
    route: Annotated[
        str | None,
        Field(description="Optional route filter (e.g., 'LAX → ORD' or 'LAX-ORD')."),
    ] = None,
) -> dict:
    """Retrieve historical and predicted payload data and return structured data."""
    historical_data = _get_historical_data()
    
    # If a route is specified, filter for that route
    if route:
        # Normalize the route string
        normalized_route = route.replace("-", " → ").replace("->", " → ")
        matching_data = [d for d in historical_data if d.get("route") == normalized_route]
        if matching_data:
            historical_data = matching_data
    
    # Separate historical and predicted data
    historical = [d for d in historical_data if not d.get("predicted", False)]
    predictions = [d for d in historical_data if d.get("predicted", False)]
    
    # Limit to requested counts
    result_data = historical[:days] + predictions[:include_predictions]
    
    historical_count = min(days, len(historical))
    predicted_count = min(include_predictions, len(predictions))
    
    if historical:
        avg_pounds = sum(d.get("pounds", 0) for d in historical[:days]) // max(1, historical_count)
    else:
        avg_pounds = 0
    
    return {
        "message": f"Historical payload data ({historical_count} days + {predicted_count} predictions). Average daily weight: {avg_pounds:,} lbs. The chart has been updated.",
        "historical_data": result_data,
    }


def create_logistics_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Instantiate the Logistics demo agent backed by Microsoft Agent Framework."""
    base_agent = ChatAgent(
        name="logistics-agent",
        instructions=dedent(
            """
            You are a shipping logistics assistant for a cargo airline company. You have FULL ACCESS to 
            the company's flight payload database through your tools.

            CRITICAL TOOL USAGE RULES:
            
            1. DATA RETRIEVAL TOOLS - Use these to get flight data:
               - get_over_utilized_flights: Get flights with >85% utilization
               - get_under_utilized_flights: Get flights with <50% utilization
               - get_optimal_flights: Get flights with optimal 50-80% utilization
               - get_predicted_payload: Get predicted payload for upcoming flights
               - get_flight_details: Get details for a specific flight number
               - get_utilization_risks: Get all flights with utilization concerns
               - get_historical_payload: Get historical trend data
            
            2. UI UPDATE TOOLS - ALWAYS call these after getting data:
               - update_flights(flights): Update the dashboard flight list
               - update_selected_flight(flight): Show a flight's detail card
               - update_historical_data(historical_data): Update the chart

            MANDATORY WORKFLOW:
            When a user asks about flights, you MUST:
            1. Call the appropriate get_* tool to retrieve the data
            2. The get_* tool returns a dict with the data
            3. IMMEDIATELY call the corresponding update_* tool with that data:
               - For flight queries: call update_flights(flights=result["flights"])
               - For flight details: call update_selected_flight(flight=result["selectedFlight"])
               - For historical/trends: call update_historical_data(historical_data=result["historical_data"])
            4. Respond with ONLY a brief insight (see response rules below)

            CHAT RESPONSE RULES - VERY IMPORTANT:
            - DO NOT list or repeat flight data in your chat response
            - The dashboard already shows all the flight details - don't duplicate them
            - Your response should be 1-3 sentences MAX with actionable insights
            - Focus on: counts, risk summary, recommendations, trends
            
            GOOD RESPONSE EXAMPLES:
            ✓ "I found 10 over-utilized flights. The LAX-ORD and DFW-ATL routes are most at risk - consider redistributing cargo."
            ✓ "Showing 8 under-utilized flights. You could consolidate shipments to improve efficiency by ~15%."
            ✓ "Here are the details for flight LAX-ORD-2847. It's at critical capacity - immediate action recommended."
            ✓ "Historical trends show a 12% increase in volume over the past week. Consider adding capacity."
            
            BAD RESPONSE EXAMPLES (NEVER DO THIS):
            ✗ "Here are the flights: LAX-ORD-1234 at 95%, DFW-ATL-5678 at 92%..." (don't list data)
            ✗ "Flight details: Weight: 45,000 lbs, Volume: 3,200 cu ft..." (dashboard shows this)

            RISK LEVELS:
            - low (< 50%): Under-utilized, consolidation opportunity
            - medium (50-80%): Optimal utilization  
            - high (80-95%): Approaching capacity
            - critical (> 95%): Over capacity, needs immediate action
            """.strip()
        ),
        chat_client=chat_client,
        tools=[
            update_flights,
            update_selected_flight,
            update_historical_data,
            get_over_utilized_flights,
            get_under_utilized_flights,
            get_optimal_flights,
            get_predicted_payload,
            get_flight_details,
            get_utilization_risks,
            get_historical_payload,
        ],
    )

    return AgentFrameworkAgent(
        agent=base_agent,
        name="logistics_agent",
        description="Manages shipping logistics data, flight payloads, and utilization analysis.",
        state_schema=STATE_SCHEMA,
        predict_state_config=PREDICT_STATE_CONFIG,
        require_confirmation=False,
        use_service_thread=False,
        orchestrators=[
            HumanInTheLoopOrchestrator(),
            DeduplicatingOrchestrator(),
        ],
    )
