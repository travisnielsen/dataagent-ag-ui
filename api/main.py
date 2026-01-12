from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager

import uvicorn
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from agent_framework._clients import ChatClientProtocol
from agent_framework import azure as _azure
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from dotenv import load_dotenv
from fastapi import FastAPI, Request

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
# Reduce agent_framework verbosity (it logs all message content at INFO level)
logging.getLogger("agent_framework").setLevel(logging.WARNING)
logging.getLogger("agent_framework_ag_ui").setLevel(logging.WARNING)
# Reduce fastapi_azure_auth verbosity
logging.getLogger("fastapi_azure_auth").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Check if Azure AD authentication is configured
AUTH_ENABLED = bool(azure_ad_settings.AZURE_AD_CLIENT_ID and azure_ad_settings.AZURE_AD_TENANT_ID)

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
        client.middleware = ResponsesApiThreadMiddleware()
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
    if AUTH_ENABLED:
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
