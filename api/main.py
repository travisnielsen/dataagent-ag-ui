from __future__ import annotations

import os
import json
import logging
import copy
import sys
from contextlib import asynccontextmanager
from typing import Optional, Any
from pathlib import Path

import uvicorn
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential


# ============================================================================
# WORKAROUND: Fix pydantic-core SchemaError with openai SDK (pydantic issue #12704)
# ============================================================================
# Pydantic 2.11+ has a bug where certain complex Union types with InstanceOf
# validators cause a SchemaError during model class creation. This affects
# the openai SDK's FinalRequestOptions.files field.
#
# The issue is tracked at: https://github.com/pydantic/pydantic/issues/12704
# Fix PR (not yet merged): https://github.com/pydantic/pydantic/pull/12705
#
# Workaround: Modify openai._types.HttpxRequestFiles before the models are loaded.
# We need to patch this BEFORE openai._models is imported.
# ============================================================================

# Import openai._types first and patch the problematic type
import openai._types as _openai_types

# Replace HttpxRequestFiles with Any to avoid pydantic schema generation errors
# Original: HttpxRequestFiles = Union[Mapping[str, HttpxFileTypes], Sequence[Tuple[str, HttpxFileTypes]]]
_openai_types.HttpxRequestFiles = Any  # type: ignore

# Now import the rest of openai modules (they'll use our patched type)
# Force reimport of _models if it was cached
if 'openai._models' in sys.modules:
    del sys.modules['openai._models']


# ============================================================================
# MONKEY-PATCH: Fix deepcopy issue in agent-framework (GitHub issue #3247)
# ============================================================================
# The agent-framework's AgentFrameworkEventBridge uses deepcopy on state dicts.
# In Azure Container Apps with Managed Identity, the credential object contains
# RLock objects that cannot be pickled/deepcopied. This patch replaces deepcopy
# with a safe JSON round-trip for dict objects.
# 
# This can be removed once the upstream fix is released.
# ============================================================================

_original_deepcopy = copy.deepcopy


def _safe_deepcopy(obj: Any, memo: dict | None = None) -> Any:
    """Safe deepcopy that handles non-copyable objects like RLock.
    
    For dicts, uses JSON round-trip which is safer and handles most state objects.
    For other types, falls back to original deepcopy with error handling.
    """
    if isinstance(obj, dict):
        try:
            # JSON round-trip is safe and handles most state dicts
            return json.loads(json.dumps(obj, default=str))
        except (TypeError, ValueError):
            pass
    
    try:
        return _original_deepcopy(obj, memo)
    except TypeError as e:
        if "RLock" in str(e) or "cannot pickle" in str(e):
            # For unpicklable objects, try JSON fallback
            if hasattr(obj, '__dict__'):
                try:
                    return json.loads(json.dumps(obj.__dict__, default=str))
                except (TypeError, ValueError):
                    pass
            # Last resort: return empty dict for state-like objects
            logging.getLogger(__name__).warning(
                "deepcopy failed for %s, returning shallow copy: %s", 
                type(obj).__name__, e
            )
            if isinstance(obj, dict):
                return {}
            return obj
        raise


# Patch the copy module's deepcopy
copy.deepcopy = _safe_deepcopy

# Also patch in the ag-ui events module directly
try:
    import agent_framework_ag_ui._events as _events_module
    _events_module.deepcopy = _safe_deepcopy
except (ImportError, AttributeError):
    pass

# Also patch in the ag-ui utils module  
try:
    import agent_framework_ag_ui._utils as _utils_module
    _utils_module.copy.deepcopy = _safe_deepcopy
except (ImportError, AttributeError):
    pass
from agent_framework._clients import ChatClientProtocol
from agent_framework import azure as _azure
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from pydantic import BaseModel

from fastapi.middleware.cors import CORSMiddleware
from agents import create_logistics_agent  # type: ignore
from middleware import (  # type: ignore
    ResponsesApiThreadMiddleware,
    azure_scheme,
    azure_ad_settings,
    AzureADAuthMiddleware,
)
from monitoring import configure_observability, is_observability_enabled  # type: ignore

# Use AzureAIClient (v2/Responses API) for Foundry Agent Service
# The ResponsesApiThreadMiddleware handles thread ID management for stateful conversations
AzureAIClient = _azure.AzureAIClient

load_dotenv()

# Configure logging to show INFO level from our modules
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
# Reduce noise from azure/httpx libraries
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# Reduce fastapi_azure_auth verbosity
logging.getLogger("fastapi_azure_auth").setLevel(logging.WARNING)
# Control agent_framework verbosity via AGENT_FRAMEWORK_LOG_LEVEL env var (default: WARNING)
agent_framework_log_level = os.getenv("AGENT_FRAMEWORK_LOG_LEVEL", "WARNING").upper()
logging.getLogger("agent_framework").setLevel(getattr(logging, agent_framework_log_level, logging.WARNING))
logging.getLogger("agent_framework_ag_ui").setLevel(getattr(logging, agent_framework_log_level, logging.WARNING))

logger = logging.getLogger(__name__)

# Check if Azure AD authentication is configured and not explicitly disabled
AUTH_ENABLED = bool(
    azure_ad_settings.AZURE_AD_CLIENT_ID 
    and azure_ad_settings.AZURE_AD_TENANT_ID
    and not azure_ad_settings.AUTH_DISABLED
)

# Configure observability before creating the app
configure_observability()

def _build_chat_client() -> ChatClientProtocol:
    """Build the AzureAIClient for Foundry Agent Service v2 (Responses API)."""
    try:
        project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        if not project_endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT environment variable is required")
        
        logger.info("Using AzureAIClient (Foundry Agent Service v2 / Responses API)")
        client = AzureAIClient(
            credential=AsyncDefaultAzureCredential(),
            project_endpoint=project_endpoint,
            model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
        )
        # Add middleware to manage response ID -> thread ID mapping for v2 Responses API
        client.middleware = [ResponsesApiThreadMiddleware()]
        return client

    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Unable to initialize the chat client. Double-check your API credentials as documented in README.md."
        ) from exc


chat_client = _build_chat_client()
logistics_agent = create_logistics_agent(chat_client)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Application lifespan handler.
    Loads Azure AD OpenID configuration on startup if auth is enabled.
    """
    # Log observability status
    if is_observability_enabled():
        logger.info("OpenTelemetry observability is ENABLED")
    else:
        logger.info("OpenTelemetry observability is disabled (set ENABLE_INSTRUMENTATION=true to enable)")
    
    # Log authentication status
    if azure_ad_settings.AUTH_DISABLED:
        logger.warning("=" * 60)
        logger.warning("WARNING: Authentication is DISABLED via AUTH_DISABLED!")
        logger.warning("The API will respond to ANONYMOUS connections.")
        logger.warning("Do NOT use this setting in production.")
        logger.warning("=" * 60)
    elif AUTH_ENABLED:
        logger.info("Azure AD authentication is ENABLED")
        if azure_scheme:
            await azure_scheme.openid_config.load_config()
    else:
        logger.warning("=" * 60)
        logger.warning("WARNING: Azure AD authentication is NOT configured!")
        logger.warning("The API will respond to ANONYMOUS connections.")
        logger.warning("Set AZURE_AD_CLIENT_ID and AZURE_AD_TENANT_ID to enable auth.")
        logger.warning("=" * 60)
    yield
    
    # Shutdown: Cleanup
    logger.info("Application shutdown complete")


app = FastAPI(
    title="CopilotKit + Microsoft Agent Framework (Python)",
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/oauth2-redirect",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True,
        "clientId": azure_ad_settings.AZURE_AD_CLIENT_ID,
    } if AUTH_ENABLED else None,
)

# IMPORTANT: Middleware runs in reverse order of addition
# CORS must be added AFTER auth so it runs FIRST (handles preflight before auth)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Azure AD auth middleware only if configured
# This runs AFTER CORS, so preflight OPTIONS requests are handled first
if AUTH_ENABLED:
    app.add_middleware(AzureADAuthMiddleware, settings=azure_ad_settings)

# Protected health check endpoint (example of how to use auth)
@app.get("/health")
async def health_check():
    """Unprotected health check endpoint."""
    return {"status": "healthy"}


@app.get("/me")
async def get_current_user(request: Request):
    """
    Protected endpoint that returns the current user's claims.
    Requires a valid Azure AD token (validated by middleware).
    """
    user = getattr(request.state, "user", None)
    if not user:
        return {"error": "Azure AD authentication not configured or user not authenticated"}
    return {
        "claims": user,
        "name": user.get("name"),
        "email": user.get("preferred_username"),
    }


# ============================================================================
# REST Data Endpoints for Bulk Data Loading
# These endpoints provide fast data access without SSE overhead
# ============================================================================

# Load flight data from JSON file
_DATA_FILE = Path(__file__).parent / "data" / "flights.json"
_FLIGHT_DATA_CACHE: dict = {}

def _load_flight_data() -> dict:
    """Load and cache flight data from the JSON file."""
    if not _FLIGHT_DATA_CACHE:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _FLIGHT_DATA_CACHE.update(data)
    return _FLIGHT_DATA_CACHE


# ============================================================================
# Feedback Models
# ============================================================================

class RecommendationFeedbackPayload(BaseModel):
    """Feedback payload for risk mitigation recommendations."""
    flightId: str
    flightNumber: str
    votes: dict[str, str]  # recommendation_id -> "up" | "down"
    comment: Optional[str] = None
    timestamp: str


class FlightsResponse(BaseModel):
    """Response model for flights endpoint."""
    flights: list[dict]
    total: int
    query: dict


class HistoricalResponse(BaseModel):
    """Response model for historical data endpoint."""
    historicalData: list[dict]
    routes: list[str]
    total: int
    query: dict


@app.get("/logistics/data/flights", response_model=FlightsResponse)
async def get_flights(
    limit: int = Query(100, ge=1, le=200, description="Maximum number of flights to return"),
    offset: int = Query(0, ge=0, description="Number of flights to skip"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level: low, medium, high, critical"),
    utilization: Optional[str] = Query(None, description="Filter by utilization: over (>95%), near_capacity (85-95%), optimal (50-85%), under (<50%)"),
    route_from: Optional[str] = Query(None, description="Filter by origin airport code"),
    route_to: Optional[str] = Query(None, description="Filter by destination airport code"),
    date_from: Optional[str] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter by end date (YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("utilizationPercent", description="Sort field"),
    sort_desc: bool = Query(True, description="Sort descending"),
):
    """
    REST endpoint for bulk flight data retrieval.
    
    This endpoint provides fast data access for initial page load and 
    agent-triggered queries without SSE overhead.
    """
    data = _load_flight_data()
    all_flights = data.get("flights", [])
    
    # Apply filters
    filtered = all_flights
    
    if risk_level:
        filtered = [f for f in filtered if f.get("riskLevel") == risk_level]
    
    if utilization:
        if utilization == "over":
            filtered = [f for f in filtered if f.get("utilizationPercent", 0) > 95]
        elif utilization == "near_capacity":
            filtered = [f for f in filtered if 85 <= f.get("utilizationPercent", 0) <= 95]
        elif utilization == "under":
            filtered = [f for f in filtered if f.get("utilizationPercent", 0) < 50]
        elif utilization == "optimal":
            filtered = [f for f in filtered if 50 <= f.get("utilizationPercent", 0) < 85]
    
    if route_from:
        filtered = [f for f in filtered if f.get("from", "").upper() == route_from.upper()]
    
    if route_to:
        filtered = [f for f in filtered if f.get("to", "").upper() == route_to.upper()]
    
    if date_from:
        filtered = [f for f in filtered if f.get("flightDate", "") >= date_from]
    
    if date_to:
        filtered = [f for f in filtered if f.get("flightDate", "") <= date_to]
    
    # Sort
    if sort_by and filtered:
        filtered = sorted(
            filtered,
            key=lambda x: x.get(sort_by, 0) if isinstance(x.get(sort_by), (int, float)) else str(x.get(sort_by, "")),
            reverse=sort_desc
        )
    
    total = len(filtered)
    
    # Apply pagination
    paginated = filtered[offset:offset + limit]
    
    return FlightsResponse(
        flights=paginated,
        total=total,
        query={
            "limit": limit,
            "offset": offset,
            "risk_level": risk_level,
            "utilization": utilization,
            "route_from": route_from,
            "route_to": route_to,
            "date_from": date_from,
            "date_to": date_to,
        }
    )


@app.get("/logistics/data/flights/{flight_id}")
async def get_flight_by_id(flight_id: str):
    """Get a specific flight by ID or flight number."""
    data = _load_flight_data()
    all_flights = data.get("flights", [])
    
    # Search by ID or flight number
    search = flight_id.upper().replace(" ", "")
    for flight in all_flights:
        if flight.get("id") == flight_id or flight.get("flightNumber", "").upper() == search:
            return {"flight": flight}
    
    return {"flight": None, "error": f"Flight {flight_id} not found"}


@app.get("/logistics/data/historical", response_model=HistoricalResponse)
async def get_historical_data(
    route_from: Optional[str] = Query(None, description="Filter by origin airport code"),
    route_to: Optional[str] = Query(None, description="Filter by destination airport code"),
    days: int = Query(10, ge=1, le=30, description="Number of days of data"),
    include_predictions: bool = Query(True, description="Include predicted data"),
):
    """
    REST endpoint for historical payload data retrieval.
    """
    data = _load_flight_data()
    historical = data.get("historicalData", [])
    
    # Apply route filter only if both from/to are specified
    if route_from and route_to:
        route_pattern = f"{route_from.upper()} → {route_to.upper()}"
        historical = [h for h in historical if h.get("route") == route_pattern]
    # If no route filter, return all historical data (for overview chart)
    
    # Filter predictions if needed
    if not include_predictions:
        historical = [h for h in historical if not h.get("predicted")]
    
    # Sort by date
    historical = sorted(historical, key=lambda x: x.get("date", ""))
    
    # Get unique routes
    unique_routes = sorted(set(h.get("route", "") for h in historical if h.get("route")))
    
    # Limit to requested days per route (if we have multiple routes)
    if not route_from or not route_to:
        # When showing all routes, limit to the most recent entries per unique route
        routes_seen: dict[str, int] = {}
        limited = []
        for h in historical:
            route = h.get("route", "aggregate")
            if routes_seen.get(route, 0) < days:
                limited.append(h)
                routes_seen[route] = routes_seen.get(route, 0) + 1
        historical = limited
    else:
        historical = historical[:days]
    
    return HistoricalResponse(
        historicalData=historical,
        routes=unique_routes,
        total=len(historical),
        query={
            "route_from": route_from,
            "route_to": route_to,
            "days": days,
            "include_predictions": include_predictions,
        }
    )


@app.get("/logistics/data/summary")
async def get_data_summary():
    """
    Get a summary of all available data for LLM context.
    Returns counts and statistics without full data.
    """
    data = _load_flight_data()
    flights = data.get("flights", [])
    
    # Calculate statistics
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    route_counts: dict[str, int] = {}
    total_utilization = 0
    
    for f in flights:
        risk = f.get("riskLevel", "unknown")
        if risk in risk_counts:
            risk_counts[risk] += 1
        
        route = f"{f.get('from', '?')} → {f.get('to', '?')}"
        route_counts[route] = route_counts.get(route, 0) + 1
        
        total_utilization += f.get("utilizationPercent", 0)
    
    avg_utilization = total_utilization / len(flights) if flights else 0
    
    # Get unique airports
    airports = set()
    for f in flights:
        airports.add(f.get("from", ""))
        airports.add(f.get("to", ""))
    airports.discard("")
    
    return {
        "totalFlights": len(flights),
        "riskBreakdown": risk_counts,
        "averageUtilization": round(avg_utilization, 1),
        "uniqueRoutes": len(route_counts),
        "topRoutes": sorted(route_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        "airports": sorted(list(airports)),
        "flightsAtRisk": risk_counts["high"] + risk_counts["critical"],
        "underUtilizedFlights": risk_counts["low"],
    }


# ============================================================================
# Feedback Endpoint
# ============================================================================

@app.post("/logistics/feedback")
async def submit_recommendation_feedback(payload: RecommendationFeedbackPayload):
    """
    Submit feedback on risk mitigation recommendations.
    
    Currently logs feedback for analysis. Backend storage will be implemented later.
    """
    logger.info("=" * 60)
    logger.info("RECOMMENDATION FEEDBACK RECEIVED")
    logger.info("=" * 60)
    logger.info("Flight ID: %s", payload.flightId)
    logger.info("Flight Number: %s", payload.flightNumber)
    logger.info("Timestamp: %s", payload.timestamp)
    logger.info("Votes: %s", json.dumps(payload.votes, indent=2))
    if payload.comment:
        logger.info("Comment: %s", payload.comment)
    logger.info("=" * 60)
    
    # TODO: Persist feedback to database/storage
    # For now, just acknowledge receipt
    
    return {
        "status": "received",
        "message": "Feedback logged successfully. Thank you!",
        "flightNumber": payload.flightNumber,
        "votesReceived": len(payload.votes),
    }


# Add the AG-UI endpoint for the logistics agent
# Mounted at /logistics to match the working configuration
add_agent_framework_fastapi_endpoint(
    app=app,
    agent=logistics_agent,
    path="/logistics",
)

if __name__ == "__main__":
    host = os.getenv("AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
