"""
Monkey patches for compatibility issues with Azure SDK and Agent Framework.

This module MUST be imported before any other imports in main.py to ensure
patches are applied before the affected libraries are loaded.

Current patches:
1. Pydantic SchemaError fix - patches openai._types.HttpxRequestFiles to avoid
   a pydantic-core bug with complex union types (pydantic issue #12704)
   
2. Deepcopy RLock fix - patches copy.deepcopy to handle Azure ManagedIdentityCredential
   objects that contain threading RLocks which cannot be pickled/deepcopied
   (Agent Framework issue #3247)
"""

import copy
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# PATCH 1: Pydantic SchemaError workaround
# ============================================================================
# Pydantic 2.11+ has a bug where complex union types with TypeAlias fail validation.
# The openai SDK's HttpxRequestFiles type triggers this during schema generation.
# We patch it to Any before importing openai._models to avoid the error.
#
# Error: SchemaError: 'cls' must be valid as the first argument to 'isinstance'
# Related: https://github.com/pydantic/pydantic/issues/12704
# ============================================================================

try:
    import openai._types
    openai._types.HttpxRequestFiles = Any  # type: ignore[attr-defined]
    logger.debug("Applied pydantic SchemaError workaround for openai._types.HttpxRequestFiles")
except (ImportError, AttributeError) as e:
    logger.warning("Failed to apply pydantic workaround: %s", e)


# ============================================================================
# PATCH 2: Deepcopy RLock workaround for Azure Managed Identity
# ============================================================================
# Azure ManagedIdentityCredential uses threading.RLock internally, which cannot
# be pickled or deepcopied. The Agent Framework uses deepcopy for state management,
# causing crashes when credentials are in the state dict.
#
# Error: TypeError: cannot pickle '_thread.RLock' object
# Related: https://github.com/Azure/agent-framework/issues/3247
# ============================================================================

_original_deepcopy = copy.deepcopy

# Track objects that failed deepcopy to skip them in future attempts
_uncopyable_ids: set[int] = set()


def _safe_deepcopy(obj: Any, memo: dict | None = None) -> Any:
    """Safe deepcopy wrapper that handles RLock errors from Azure credentials.
    
    When deepcopy fails on an object with RLock, we mark that object and return
    the original (shallow reference). This preserves tools and other complex objects.
    """
    # If this exact object failed before, return it as-is
    if id(obj) in _uncopyable_ids:
        return obj
    
    try:
        return _original_deepcopy(obj, memo)
    except TypeError as e:
        if "RLock" in str(e) or "cannot pickle" in str(e):
            # Mark this object as uncopyable for future calls
            _uncopyable_ids.add(id(obj))
            
            # For dicts, try to copy what we can, keeping references to uncopyable items
            if isinstance(obj, dict):
                if memo is None:
                    memo = {}
                result = {}
                for k, v in obj.items():
                    try:
                        result[k] = _safe_deepcopy(v, memo)
                    except TypeError:
                        # Keep the original reference for uncopyable values
                        result[k] = v
                        _uncopyable_ids.add(id(v))
                return result
            
            # For other objects, return original reference
            logger.debug(
                "deepcopy RLock error for %s, returning original reference", type(obj).__name__
            )
            return obj
        raise


def apply_deepcopy_patch() -> None:
    """Apply the deepcopy patch globally and to framework modules."""
    # Patch copy.deepcopy globally
    copy.deepcopy = _safe_deepcopy
    
    # CRITICAL: Also patch the local references in framework modules
    # These modules do "from copy import deepcopy" at import time, binding to the original
    # We must update their module namespace to point to our patched version
    try:
        import agent_framework_ag_ui._events as _events_module
        _events_module.deepcopy = _safe_deepcopy
        logger.debug("Patched agent_framework_ag_ui._events.deepcopy")
    except (ImportError, AttributeError):
        pass

    try:
        import agent_framework_ag_ui._utils as _utils_module
        _utils_module.copy.deepcopy = _safe_deepcopy
        logger.debug("Patched agent_framework_ag_ui._utils.copy.deepcopy")
    except (ImportError, AttributeError):
        pass

    try:
        import agent_framework_ag_ui._endpoint as _endpoint_module
        _endpoint_module.copy.deepcopy = _safe_deepcopy
        logger.debug("Patched agent_framework_ag_ui._endpoint.copy.deepcopy")
    except (ImportError, AttributeError):
        pass
    
    logger.debug("Applied deepcopy RLock workaround for Azure credentials")


# Apply the deepcopy patch immediately on import
apply_deepcopy_patch()
