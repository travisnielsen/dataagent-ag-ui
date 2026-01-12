"""Middleware and orchestrators for AG-UI + v2 Responses API integration."""

from .auth import (
    AzureADSettings,
    AzureADAuthMiddleware,
    azure_ad_settings,
    azure_scheme,
    get_azure_auth_scheme,
)
from .responses_api import (
    ResponsesApiThreadMiddleware,
    get_thread_response_store,
    get_current_agui_thread_id,
)
from .orchestrators import DeduplicatingOrchestrator

__all__ = [
    # Auth
    "AzureADSettings",
    "AzureADAuthMiddleware",
    "azure_ad_settings",
    "azure_scheme",
    "get_azure_auth_scheme",
    # Responses API middleware
    "ResponsesApiThreadMiddleware",
    "get_thread_response_store",
    "get_current_agui_thread_id",
    # Orchestrators
    "DeduplicatingOrchestrator",
]
