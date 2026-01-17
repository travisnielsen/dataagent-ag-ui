"""
Logistics Agent with Microsoft Agent Framework

This module defines the logistics agent configuration, tools, and state schema
for the shipping logistics demo backed by v2 Responses API.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from pathlib import Path
from textwrap import dedent
from typing import Annotated

from agent_framework import ChatAgent, ChatClientProtocol, ai_function
from agent_framework_ag_ui import AgentFrameworkAgent
from agent_framework_ag_ui._orchestrators import HumanInTheLoopOrchestrator
from pydantic import Field

from middleware import DeduplicatingOrchestrator

logger = logging.getLogger(__name__)

# ContextVar to pass current filter from request to tools
# This allows tools to automatically use the current dashboard filter
current_active_filter: ContextVar[dict | None] = ContextVar("current_active_filter", default=None)

# ContextVar to pass selected flight from request to tools
# This allows tools to automatically analyze the selected flight when user asks about "this flight"
current_selected_flight: ContextVar[dict | None] = ContextVar("current_selected_flight", default=None)


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
            "routeFrom": {"type": "string", "description": "Origin airport code (e.g., LAX)"},
            "routeTo": {"type": "string", "description": "Destination airport code (e.g., ORD)"},
            "utilizationType": {"type": "string", "enum": ["all", "over", "near_capacity", "optimal", "under"]},
            "riskLevel": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "dateFrom": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
            "dateTo": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            "limit": {"type": "number", "description": "Max flights to return"},
        },
        "description": "Active filter for the flight list. Frontend reacts to this and fetches data via REST.",
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
    # fetch_flights and clear_filter update activeFilter - frontend reacts and fetches via REST
    "activeFilter": {
        "tool": "fetch_flights",
        "tool_argument": "activeFilter",
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
    name="fetch_flights",
    description="COMMAND TOOL: Load and filter flights in the dashboard. Use for commands like 'show me', 'load', 'filter by', 'display'. Sets the filter state and the frontend fetches data via REST API. Use reset=true for new queries, reset=false to refine current view.",
)
def fetch_flights(
    route_from: Annotated[
        str | None,
        Field(description="Origin airport code (e.g., LAX)"),
    ] = None,
    route_to: Annotated[
        str | None,
        Field(description="Destination airport code (e.g., ORD)"),
    ] = None,
    utilization: Annotated[
        str | None,
        Field(description="Utilization filter: 'over' (>95% capacity), 'near_capacity' (85-95%), 'optimal' (50-85%), 'under' (<50%). Use 'over' for over capacity flights."),
    ] = None,
    risk_level: Annotated[
        str | None,
        Field(description="Risk level filter: critical, high, medium, low"),
    ] = None,
    date_from: Annotated[
        str | None,
        Field(description="Start date (YYYY-MM-DD)"),
    ] = None,
    date_to: Annotated[
        str | None,
        Field(description="End date (YYYY-MM-DD)"),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="Max flights to return (default 100, max 100)"),
    ] = None,
    reset: Annotated[
        bool,
        Field(description="True = fresh query (clears existing filters). False = refine current view (add to existing filters)."),
    ] = True,
) -> dict:
    """Set the filter state. Frontend reacts and fetches data via REST API."""
    max_limit = min(limit or 100, 100) if limit else 100
    
    # Build the filter object that frontend will use
    # When reset=false, None values mean "keep existing" (frontend handles merge)
    active_filter = {
        "routeFrom": route_from.upper() if route_from else (None if reset else "__KEEP__"),
        "routeTo": route_to.upper() if route_to else (None if reset else "__KEEP__"),
        "utilizationType": utilization if utilization else (None if reset else "__KEEP__"),
        "riskLevel": risk_level.lower() if risk_level else (None if reset else "__KEEP__"),
        "dateFrom": date_from if date_from else (None if reset else "__KEEP__"),
        "dateTo": date_to if date_to else (None if reset else "__KEEP__"),
        "limit": max_limit,
        "reset": reset,
    }
    
    # CRITICAL: Update the current_active_filter ContextVar so that if analyze_flights
    # is called in the same turn, it uses the NEW filter, not the old one from request start
    cleaned_filter = {
        k: (None if v == "__KEEP__" else v)
        for k, v in active_filter.items()
    }
    current_active_filter.set(cleaned_filter)
    logger.info("[fetch_flights] Updated current_active_filter ContextVar: %s", cleaned_filter)
    
    # Build description for user
    filter_parts = []
    if route_from:
        filter_parts.append(f"from {route_from.upper()}")
    if route_to:
        filter_parts.append(f"to {route_to.upper()}")
    if utilization:
        filter_parts.append(utilization)
    if risk_level:
        filter_parts.append(f"{risk_level} risk")
    if date_from:
        filter_parts.append(f"from {date_from}")
    if date_to:
        filter_parts.append(f"to {date_to}")
    
    filter_desc = ', '.join(filter_parts) if filter_parts else 'all flights'
    
    return {
        "message": f"Loading flights: {filter_desc} (max {max_limit}). Dashboard is updating...",
        "activeFilter": active_filter,
    }


@ai_function(
    name="clear_filter",
    description="COMMAND TOOL: Clear all filters and show all flights. Use for 'show all', 'reset', 'clear filter'.",
)
def clear_filter(
    limit: Annotated[
        int | None,
        Field(description="Max flights to return (default 100, max 100)"),
    ] = None,
) -> dict:
    """Clear all filters. Frontend reacts and fetches all data via REST API."""
    max_limit = min(limit or 100, 100) if limit else 100
    
    # Clear the current_active_filter ContextVar to None (not a dict with nulls)
    # This ensures analyze_flights sees no filter is active
    current_active_filter.set(None)
    logger.info("[clear_filter] Cleared current_active_filter ContextVar to None")
    
    # Return cleared filter object for frontend state
    cleared_filter = {
        "routeFrom": None,
        "routeTo": None,
        "utilizationType": None,
        "riskLevel": None,
        "dateFrom": None,
        "dateTo": None,
        "limit": max_limit,
    }
    
    return {
        "message": f"Clearing all filters. Loading up to {max_limit} flights...",
        "activeFilter": cleared_filter,
    }


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


def _get_flight_by_id_or_number(identifier: str) -> dict | None:
    """Helper to find a flight by ID or flight number."""
    all_flights = _get_all_flights()
    search = identifier.upper().replace(" ", "")
    
    for flight in all_flights:
        if flight.get("id") == identifier or flight.get("flightNumber", "").upper() == search:
            return flight
    return None


@ai_function(
    name="show_risk_recommendations",
    description="Display risk mitigation recommendations for a high-risk or critical flight. Shows interactive recommendations in the chat with feedback options. Use when user asks about recommendations, mitigation strategies, or what to do about a risky flight. Can also show optimization suggestions for under-utilized (low risk) flights.",
)
def show_risk_recommendations(
    flight_id: Annotated[
        str | None,
        Field(description="ID or flight number of the flight to show recommendations for. If not provided, uses the currently selected flight from the UI."),
    ] = None,
) -> dict:
    """Generate and return recommendations for a flight. Rendered as interactive card in chat."""
    from datetime import datetime
    
    # Determine which flight to analyze
    flight = None
    
    # Priority 1: Explicit flight_id parameter
    if flight_id:
        flight = _get_flight_by_id_or_number(flight_id)
    
    # Priority 2: Currently selected flight from UI
    if not flight:
        selected = current_selected_flight.get()
        if selected:
            flight = selected
    
    if not flight:
        return {
            "error": "No flight specified or selected. Please select a flight or provide a flight number.",
            "recommendations": [],
        }
    
    flight_number = flight.get("flightNumber", "unknown")
    risk_level = flight.get("riskLevel", "medium")
    utilization = flight.get("utilizationPercent", 0)
    route = f"{flight.get('from', '?')} → {flight.get('to', '?')}"
    
    # Generate recommendations based on risk level
    recommendations = []
    
    if risk_level in ("high", "critical"):
        # High/critical risk - mitigation recommendations
        recommendations = [
            {
                "id": "rec-redistribute",
                "text": "Redistribute cargo to under-utilized flights on similar routes",
                "category": "redistribution",
            },
            {
                "id": "rec-defer",
                "text": "Review shipment priorities and defer non-critical packages to next available flight",
                "category": "deferral",
            },
            {
                "id": "rec-expand",
                "text": "Contact operations to explore capacity expansion options (larger aircraft, additional flight)",
                "category": "expansion",
            },
        ]
        
        # Add specific recommendations based on utilization
        if utilization > 95:
            recommendations.insert(0, {
                "id": "rec-immediate",
                "text": f"URGENT: Flight is at {utilization:.1f}% capacity. Immediate action required to prevent delays",
                "category": "redistribution",
            })
    
    elif risk_level == "low":
        # Low risk - optimization recommendations  
        recommendations = [
            {
                "id": "rec-consolidate",
                "text": "Consolidate shipments from over-utilized routes to maximize this flight's capacity",
                "category": "consolidation",
            },
            {
                "id": "rec-cost-opt",
                "text": "Opportunity for cost optimization through better load balancing across network",
                "category": "optimization",
            },
            {
                "id": "rec-accept-more",
                "text": f"Flight has {100 - utilization:.1f}% available capacity - can accept additional cargo",
                "category": "optimization",
            },
        ]
    
    else:
        # Medium risk - no urgent recommendations
        return {
            "flightId": flight.get("id", ""),
            "flightNumber": flight_number,
            "route": route,
            "riskLevel": risk_level,
            "utilizationPercent": utilization,
            "recommendations": [],
            "message": f"Flight {flight_number} is at optimal utilization ({utilization:.1f}%). No action needed.",
            "generatedAt": datetime.utcnow().isoformat() + "Z",
        }
    
    logger.info("[show_risk_recommendations] Generated %d recommendations for flight %s (%s risk)",
                len(recommendations), flight_number, risk_level)
    
    return {
        "flightId": flight.get("id", ""),
        "flightNumber": flight_number,
        "route": route,
        "riskLevel": risk_level,
        "utilizationPercent": utilization,
        "recommendations": recommendations,
        "generatedAt": datetime.utcnow().isoformat() + "Z",
    }


@ai_function(
    name="analyze_flights",
    description="""Answer questions about flights by analyzing data. 
    
CRITICAL: When the user's question mentions a SPECIFIC utilization type or risk level, you MUST pass it as a parameter:
- "how many flights are near capacity?" → utilization_filter="near_capacity"
- "which routes are over capacity?" → utilization_filter="over"  
- "how many high risk flights?" → risk_level="high"
- "tell me about critical risk flights" → risk_level="critical"

Only use no parameters when the question is about "all flights" or "these flights" (current view) with no specific filter mentioned.""",
)
def analyze_flights(
    utilization_filter: Annotated[
        str | None,
        Field(description="REQUIRED when question mentions utilization. Use: 'over', 'near_capacity', 'optimal', 'under'. Example: 'near capacity flights' → 'near_capacity'"),
    ] = None,
    risk_level: Annotated[
        str | None,
        Field(description="REQUIRED when question mentions risk. Use: 'critical', 'high', 'medium', 'low'. Example: 'high risk flights' → 'high'"),
    ] = None,
    route_from: Annotated[
        str | None,
        Field(description="Origin airport code filter (e.g., 'LAX'), or null for all origins."),
    ] = None,
    route_to: Annotated[
        str | None,
        Field(description="Destination airport code filter (e.g., 'ORD'), or null for all destinations."),
    ] = None,
    date_from: Annotated[
        str | None,
        Field(description="Start date filter (YYYY-MM-DD), or null for no date filter."),
    ] = None,
    date_to: Annotated[
        str | None,
        Field(description="End date filter (YYYY-MM-DD), or null for no date filter."),
    ] = None,
    question: Annotated[
        str,
        Field(description="The user's question about the data."),
    ] = "general summary",
) -> dict:
    """Analyze flight data based on explicit parameters. Pass filter params when question mentions specific criteria."""
    all_flights = _get_all_flights()
    
    # Log what parameters were passed
    logger.info("[analyze_flights] Called with: utilization=%s, risk=%s, route=%s->%s, question=%s",
                utilization_filter, risk_level, route_from, route_to, question)
    
    # Get current filter from ContextVar (set by orchestrator at request start)
    active_filter = current_active_filter.get()
    selected_flight = current_selected_flight.get()
    
    logger.info("[analyze_flights] ContextVar state: active_filter=%s, selected_flight=%s",
                active_filter, selected_flight.get('flightNumber') if selected_flight else None)
    
    # PRIORITY 1: Check if user has a specific flight selected (viewing detail card)
    # If so, analyze just that flight - this handles "tell me about this flight" queries
    if selected_flight and not any([utilization_filter, route_from, route_to, risk_level, date_from, date_to]):
        flight_number = selected_flight.get('flightNumber', 'unknown')
        logger.info("[analyze_flights] Analyzing selected flight: %s", flight_number)
        
        # Return detailed analysis of the selected flight
        utilization = selected_flight.get('utilizationPercent', 0)
        risk = selected_flight.get('riskLevel', 'unknown')
        current_lbs = selected_flight.get('currentPounds', 0)
        max_lbs = selected_flight.get('maxPounds', 0)
        current_cf = selected_flight.get('currentCubicFeet', 0)
        max_cf = selected_flight.get('maxCubicFeet', 0)
        route = f"{selected_flight.get('from', '?')} → {selected_flight.get('to', '?')}"
        flight_date = selected_flight.get('flightDate', 'unknown')
        sort_time = selected_flight.get('sortTime', 'unknown')
        
        # Determine capacity status
        if utilization > 95:
            capacity_status = "over capacity - requires immediate attention"
        elif utilization >= 85:
            capacity_status = "near capacity - monitor closely"
        elif utilization >= 50:
            capacity_status = "optimal utilization"
        else:
            capacity_status = "under-utilized - opportunity for consolidation"
        
        return {
            "analysis_type": "selected_flight",
            "flight_number": flight_number,
            "route": route,
            "flight_date": flight_date,
            "sort_time": sort_time,
            "utilization_percent": utilization,
            "capacity_status": capacity_status,
            "risk_level": risk,
            "weight": {
                "current_pounds": current_lbs,
                "max_pounds": max_lbs,
                "available_pounds": max_lbs - current_lbs,
            },
            "volume": {
                "current_cubic_feet": current_cf,
                "max_cubic_feet": max_cf,
                "available_cubic_feet": max_cf - current_cf,
            },
            "question": question,
        }
    
    # PRIORITY 2: Use current dashboard filter if no explicit filters provided
    # This ensures we analyze exactly what the user sees without LLM needing to pass params
    
    # Helper to clean __KEEP__ sentinel values (fallback in case orchestrator didn't clean them)
    def clean_value(v):
        return None if v == "__KEEP__" else v
    
    # Check if active_filter has any meaningful (non-null) filter values
    # A cleared filter with all None values should be treated as "no filter"
    def has_meaningful_filter(f):
        if not f:
            return False
        # Check if any filter field has a non-null value (excluding limit)
        return any([
            f.get("routeFrom"),
            f.get("routeTo"),
            f.get("utilizationType"),
            f.get("riskLevel"),
            f.get("dateFrom"),
            f.get("dateTo"),
        ])
    
    has_active_filter = has_meaningful_filter(active_filter)
    logger.info("[analyze_flights] has_meaningful_filter=%s", has_active_filter)
    
    # Only use dashboard filter if NO explicit params were passed AND there's a meaningful filter
    # This prevents stale filter context from affecting results when user passes explicit criteria
    if has_active_filter and not any([utilization_filter, route_from, route_to, risk_level, date_from, date_to]):
        # No explicit filters passed - use current dashboard filter automatically
        logger.info("[analyze_flights] Using current dashboard filter automatically")
        route_from = clean_value(active_filter.get("routeFrom"))
        route_to = clean_value(active_filter.get("routeTo"))
        utilization_filter = clean_value(active_filter.get("utilizationType"))
        risk_level = clean_value(active_filter.get("riskLevel"))
        date_from = clean_value(active_filter.get("dateFrom"))
        date_to = clean_value(active_filter.get("dateTo"))
        logger.info("[analyze_flights] After applying filter: route=%s->%s, util=%s, risk=%s",
                    route_from, route_to, utilization_filter, risk_level)
    
    # Start with all flights
    flights = all_flights
    
    # Apply utilization filter
    if utilization_filter == 'over':
        flights = [f for f in flights if f.get('utilizationPercent', 0) > 95]
    elif utilization_filter == 'near_capacity':
        flights = [f for f in flights if 85 <= f.get('utilizationPercent', 0) <= 95]
    elif utilization_filter == 'optimal':
        flights = [f for f in flights if 50 <= f.get('utilizationPercent', 0) < 85]
    elif utilization_filter == 'under':
        flights = [f for f in flights if f.get('utilizationPercent', 0) < 50]
    
    # Apply route filters (separate from/to)
    if route_from:
        flights = [f for f in flights if f.get('from', '').upper() == route_from.upper()]
    if route_to:
        flights = [f for f in flights if f.get('to', '').upper() == route_to.upper()]
    
    # Apply risk level filter
    if risk_level:
        flights = [f for f in flights if f.get('riskLevel') == risk_level.lower()]
    
    # Apply date filters
    if date_from:
        flights = [f for f in flights if f.get('flightDate', '') >= date_from]
    if date_to:
        flights = [f for f in flights if f.get('flightDate', '') <= date_to]
    
    if not flights:
        filter_parts = []
        if utilization_filter:
            filter_parts.append(f"utilization={utilization_filter}")
        if route_from:
            filter_parts.append(f"from={route_from}")
        if route_to:
            filter_parts.append(f"to={route_to}")
        if risk_level:
            filter_parts.append(f"risk={risk_level}")
        if date_from or date_to:
            filter_parts.append(f"dates={date_from or '*'} to {date_to or '*'}")
        filter_str = ', '.join(filter_parts) if filter_parts else 'none'
        return {
            "message": f"No flights match the filter ({filter_str}).",
            "analysis": "No data to analyze."
        }
    
    # Calculate comprehensive stats
    total = len(flights)
    avg_util = sum(f.get('utilizationPercent', 0) for f in flights) / total
    
    # Risk breakdown
    critical = len([f for f in flights if f.get('riskLevel') == 'critical'])
    high = len([f for f in flights if f.get('riskLevel') == 'high'])
    medium = len([f for f in flights if f.get('riskLevel') == 'medium'])
    low = len([f for f in flights if f.get('riskLevel') == 'low'])
    
    # Route breakdown
    route_counts: dict[str, int] = {}
    for f in flights:
        route = f"{f.get('from')} → {f.get('to')}"
        route_counts[route] = route_counts.get(route, 0) + 1
    
    routes_sorted = sorted(route_counts.items(), key=lambda x: x[1], reverse=True)
    top_route = routes_sorted[0] if routes_sorted else ("N/A", 0)
    
    # Build filter description
    filter_parts = []
    if utilization_filter:
        filter_parts.append(f"utilization={utilization_filter}")
    if route_from:
        filter_parts.append(f"from={route_from}")
    if route_to:
        filter_parts.append(f"to={route_to}")
    if risk_level:
        filter_parts.append(f"risk={risk_level}")
    if date_from or date_to:
        filter_parts.append(f"dates={date_from or '*'} to {date_to or '*'}")
    
    # Make it clear to the LLM what data scope we're analyzing
    if filter_parts:
        filter_str = f" (filtered by: {', '.join(filter_parts)})"
        scope_msg = f"Analyzing {total} flights with {', '.join(filter_parts)}"
    else:
        filter_str = " (ALL flights in system - no filter applied)"
        scope_msg = f"Analyzing ALL {total} flights in the system (no route or utilization filter active)"
    
    logger.info("[analyze_flights] %s", scope_msg)
    
    analysis = f"""{scope_msg}:
- Average utilization: {avg_util:.1f}%
- Risk levels: {critical} critical, {high} high, {medium} medium, {low} low
- Top route: {top_route[0]} with {top_route[1]} flights
- Route breakdown: {', '.join(f'{r}: {c}' for r, c in routes_sorted[:5])}"""
    
    return {
        "message": analysis,
        "stats": {
            "totalFlights": total,
            "averageUtilization": round(avg_util, 1),
            "riskBreakdown": {"critical": critical, "high": high, "medium": medium, "low": low},
            "topRoute": {"route": top_route[0], "count": top_route[1]},
            "routeCounts": dict(routes_sorted[:10]),
        }
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
            You are a shipping logistics assistant with access to flight payload data.

            CRITICAL: You MUST call a tool for EVERY user request. NEVER respond with just text.
            
            TOOL SELECTION:
            
            CATEGORY A - COMMANDS (change what's displayed):
            Triggers: "show me", "load", "filter", "display", "find"
            Tool: fetch_flights (filters dashboard - frontend fetches via REST API)
            Response: Brief confirmation after tool completes
            
            CATEGORY B - RESET:
            Triggers: "show all", "reset", "clear", "start over"
            Tool: clear_filter (clears all filters)
            Response: Brief confirmation
            
            CATEGORY C - QUESTIONS ABOUT SPECIFIC SUBSETS:
            When user asks about flights with SPECIFIC criteria (utilization type, risk level, route):
            - "how many flights are near capacity?" 
            - "which routes are over capacity?"
            - "what high risk flights are there?"
            
            IMPORTANT: Call BOTH tools in sequence:
            1. fetch_flights - to update the dashboard to show those flights
            2. analyze_flights - to get the analysis for your response
            
            This ensures the dashboard reflects what you're talking about.
            
            CATEGORY D - GENERAL QUESTIONS (about current view):
            Triggers: "tell me about these", "what can you see", "analyze this", "insights"
            Tool: analyze_flights ONLY (no filter change needed - analyze current view)
            Response: Summarize insights in 1-2 sentences
            
            CATEGORY E - RECOMMENDATIONS:
            Triggers: "recommendations", "what should I do", "how to fix", "mitigate", "optimize"
            Tool: show_risk_recommendations
            Response: The recommendations card will appear with feedback options.
            
            EXAMPLES:
            - "show me LAX to ORD" → fetch_flights(route_from="LAX", route_to="ORD")
            - "how many flights are near capacity?" → fetch_flights(utilization="near_capacity") THEN analyze_flights(utilization_filter="near_capacity")
            - "which routes are over capacity?" → fetch_flights(utilization="over") THEN analyze_flights(utilization_filter="over")
            - "tell me about these flights" → analyze_flights() (current view)
            - "give me recommendations" → show_risk_recommendations
            
            FETCH_FLIGHTS PARAMETERS:
            - route_from: Origin airport (e.g., "LAX")
            - route_to: Destination airport (e.g., "ORD")
            - utilization: "over", "near_capacity", "optimal", "under"
            - risk_level: "critical", "high", "medium", "low"
            - limit: Number of flights (default 100, max 100)
            
            ANALYZE_FLIGHTS PARAMETERS:
            - utilization_filter: "over", "near_capacity", "optimal", "under"
            - risk_level: "critical", "high", "medium", "low"
            - route_from, route_to: Filter by route
            - question: The user's question
            
            UTILIZATION: over (>95%), near_capacity (85-95%), optimal (50-85%), under (<50%)
            """.strip()
        ),
        chat_client=chat_client,
        tools=[
            # Dashboard filter tools - these set activeFilter in state
            # The frontend's useRenderToolCall triggers immediate REST fetch on tool start
            fetch_flights,
            clear_filter,
            # Backend tools for state updates (used internally)
            update_flights,
            update_selected_flight,
            update_historical_data,
            # Analysis tools - answer questions about data
            analyze_flights,
            # Recommendations with feedback
            show_risk_recommendations,
            # Chart data tools
            get_historical_payload,
            get_predicted_payload,
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
