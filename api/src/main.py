from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager

import uvicorn
from azure.identity import DefaultAzureCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from agent_framework._clients import ChatClientProtocol
from agent_framework.azure._chat_client import AzureOpenAIChatClient
from agent_framework.azure import AzureAIAgentClient # type: ignore
from agent_framework.openai import OpenAIChatClient
from agent_framework_ag_ui import add_agent_framework_fastapi_endpoint
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

from agent import create_agent # type: ignore
from auth import azure_scheme, azure_ad_settings, AzureADAuthMiddleware # type: ignore

load_dotenv()

logger = logging.getLogger(__name__)

# Check if Azure AD authentication is configured
AUTH_ENABLED = bool(azure_ad_settings.AZURE_AD_CLIENT_ID and azure_ad_settings.AZURE_AD_TENANT_ID)

def _build_chat_client() -> ChatClientProtocol:
    """
    Build the appropriate chat client based on environment configuration.
    
    Set USE_FOUNDRY_AGENT=true to use AzureAIAgentClient (enables Foundry integration, threads).
    Otherwise, uses AzureOpenAIChatClient (stateless, no Foundry integration).
    """
    use_foundry = os.getenv("USE_FOUNDRY_AGENT", "false").lower() == "true"
    
    try:
        if use_foundry and os.getenv("AZURE_AI_PROJECT_ENDPOINT"):
            # Azure AI Foundry Agent - enables thread management and Foundry visibility
            # Uses async credential for async operations
            # 
            # NOTE: AzureAIAgentClient creates a new Foundry thread for each request
            # when no thread_id is provided. For stateless operation (like AG-UI where
            # thread state is managed by the protocol), we need AzureOpenAIChatClient.
            # The AzureAIAgentClient is meant for scenarios where you want Foundry's
            # built-in thread management.
            # see: https://github.com/microsoft/agent-framework/issues/2479
            logger.warning(
                "AzureAIAgentClient creates new Foundry threads per request. "
                "For stateless AG-UI operation, consider using AzureOpenAIChatClient instead."
            )
            return AzureAIAgentClient(
                credential=AsyncDefaultAzureCredential(),
                project_endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
                model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
            )
        elif bool(os.getenv("AZURE_OPENAI_ENDPOINT")):
            # Azure OpenAI Chat - stateless, no Foundry integration
            # Uses sync credential
            logger.info("Using AzureOpenAIChatClient (stateless mode)")
            return AzureOpenAIChatClient(
                credential=DefaultAzureCredential(),
                endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                deployment_name=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini"),
            )

        raise ValueError("Either AZURE_OPENAI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")

    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Unable to initialize the chat client. Double-check your API credentials as documented in README.md."
        ) from exc


chat_client = _build_chat_client()
my_agent = create_agent(chat_client)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Application lifespan handler.
    Loads Azure AD OpenID configuration on startup if auth is enabled.
    """
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


app = FastAPI(
    title="CopilotKit + Microsoft Agent Framework (Python)",
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/oauth2-redirect",
    swagger_ui_init_oauth={
        "usePkceWithAuthorizationCodeGrant": True,
        "clientId": azure_ad_settings.AZURE_AD_CLIENT_ID,
    } if AUTH_ENABLED else None,
)

# Add Azure AD auth middleware only if configured
if AUTH_ENABLED:
    app.add_middleware(AzureADAuthMiddleware, settings=azure_ad_settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


add_agent_framework_fastapi_endpoint(
    app=app,
    agent=my_agent,
    path="/",
)

if __name__ == "__main__":
    host = os.getenv("AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("AGENT_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
