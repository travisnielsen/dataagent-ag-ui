"""
Logistics Agent with Microsoft Agent Framework

This module defines the logistics agent configuration, tools, and state schema
for the shipping logistics demo backed by v2 Responses API.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from textwrap import dedent
from typing import Annotated, Literal

from agent_framework import ChatAgent, ChatClientProtocol, ai_function
from agent_framework_ag_ui import AgentFrameworkAgent
from agent_framework_ag_ui._orchestrators import HumanInTheLoopOrchestrator
from pydantic import Field

from middleware import DeduplicatingOrchestrator


# Demo date - fixed for consistent demo presentations
# Change this date when you want to update the "current" date for demos
DEMO_DATE = datetime(2026, 1, 11)


# Mock data generators
AIRPORTS = [
    ("LAX", "Los Angeles"),
    ("ORD", "Chicago"),
    ("JFK", "New York"),
    ("DFW", "Dallas"),
    ("ATL", "Atlanta"),
    ("SFO", "San Francisco"),
    ("SEA", "Seattle"),
    ("MIA", "Miami"),
    ("DEN", "Denver"),
    ("PHX", "Phoenix"),
]

SORT_TIMES = ["06:00", "10:00", "14:00", "18:00", "22:00"]


def _generate_flight_number(from_code: str, to_code: str) -> str:
    """Generate a flight number."""
    return f"{from_code}-{to_code}-{random.randint(1000, 9999)}"


def _calculate_risk_level(utilization: float) -> str:
    """Calculate risk level based on utilization percentage."""
    if utilization < 50:
        return "low"
    elif utilization < 80:
        return "medium"
    elif utilization < 95:
        return "high"
    else:
        return "critical"


def _generate_mock_flight(
    bias: Literal["over", "under", "mixed", "risk"] = "mixed",
    flight_number: str | None = None,
) -> dict:
    """Generate a mock flight with realistic data."""
    from_airport = random.choice(AIRPORTS)
    to_airport = random.choice([a for a in AIRPORTS if a[0] != from_airport[0]])
    
    max_pounds = random.randint(40000, 80000)
    max_cubic_feet = random.randint(3000, 6000)
    
    # Generate utilization based on bias
    if bias == "over":
        utilization = random.uniform(85, 110)  # Can be over 100%
    elif bias == "under":
        utilization = random.uniform(20, 50)
    elif bias == "risk":
        utilization = random.choice([
            random.uniform(20, 45),   # Under-utilized
            random.uniform(85, 110),  # Over-utilized
        ])
    else:
        utilization = random.uniform(30, 105)
    
    current_pounds = int(max_pounds * utilization / 100)
    current_cubic_feet = int(max_cubic_feet * utilization / 100)
    
    return {
        "id": f"flight-{random.randint(10000, 99999)}",
        "flightNumber": flight_number or _generate_flight_number(from_airport[0], to_airport[0]),
        "flightDate": (DEMO_DATE + timedelta(days=random.randint(0, 3))).strftime("%m/%d/%Y"),
        "from": from_airport[0],
        "to": to_airport[0],
        "currentPounds": current_pounds,
        "maxPounds": max_pounds,
        "currentCubicFeet": current_cubic_feet,
        "maxCubicFeet": max_cubic_feet,
        "utilizationPercent": round(min(utilization, 100), 1),
        "riskLevel": _calculate_risk_level(utilization),
        "sortTime": random.choice(SORT_TIMES),
    }


def _generate_historical_data(days: int = 7, include_predictions: int = 3) -> list[dict]:
    """Generate historical and predicted payload data."""
    data = []
    base_date = DEMO_DATE
    
    # Historical data
    for i in range(days, 0, -1):
        date = base_date - timedelta(days=i)
        data.append({
            "date": date.strftime("%m/%d"),
            "pounds": random.randint(35000, 65000),
            "cubicFeet": random.randint(2500, 5000),
            "predicted": False,
        })
    
    # Predictions
    for i in range(include_predictions):
        date = base_date + timedelta(days=i + 1)
        data.append({
            "date": date.strftime("%m/%d"),
            "pounds": random.randint(40000, 60000),
            "cubicFeet": random.randint(2800, 4800),
            "predicted": True,
        })
    
    return data


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
    flights = [_generate_mock_flight(bias="over") for _ in range(count)]
    return {
        "message": f"Found {count} over-utilized flights. The dashboard has been updated.",
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
    flights = [_generate_mock_flight(bias="under") for _ in range(count)]
    return {
        "message": f"Found {count} under-utilized flights. The dashboard has been updated.",
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
    flights = [_generate_mock_flight(bias="mixed") for _ in range(count)]
    return {
        "message": f"Predicted payload for {count} upcoming flights. The dashboard has been updated.",
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
    # Parse flight number to get airports
    parts = flight_number.upper().replace(" ", "").split("-")
    if len(parts) >= 2:
        from_code = parts[0]
        to_code = parts[1]
    else:
        from_code = "LAX"
        to_code = "ORD"
    
    flight = _generate_mock_flight(flight_number=flight_number)
    flight["from"] = from_code
    flight["to"] = to_code
    
    return {
        "message": f"Showing details for flight {flight['flightNumber']}.",
        "selectedFlight": flight,
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
    flights = [_generate_mock_flight(bias="risk") for _ in range(count)]
    
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
) -> dict:
    """Retrieve historical and predicted payload data and return structured data."""
    data = _generate_historical_data(days, include_predictions)
    
    historical = [d for d in data if not d["predicted"]]
    predictions = [d for d in data if d["predicted"]]
    
    avg_pounds = sum(d["pounds"] for d in historical) // len(historical)
    
    return {
        "message": f"Historical payload data ({days} days + {include_predictions} predictions). Average daily weight: {avg_pounds:,} lbs. The chart has been updated.",
        "historical_data": data,
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
            get_predicted_payload,
            get_flight_details,
            get_utilization_risks,
            get_historical_payload,
        ],
    )

    return AgentFrameworkAgent(
        agent=base_agent,
        name="CopilotKitLogisticsAgent",
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
