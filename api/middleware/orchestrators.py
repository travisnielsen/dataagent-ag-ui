"""
Custom Orchestrators for AG-UI Protocol

This module provides custom orchestrators that wrap the default AG-UI orchestrators
to handle v2 Responses API compatibility issues.
"""

from __future__ import annotations

import json
import logging

from agent_framework_ag_ui._orchestrators import DefaultOrchestrator, Orchestrator, ExecutionContext
from agent_framework._types import FunctionCallContent, FunctionResultContent
from ag_ui.core import (
    RunStartedEvent, RunFinishedEvent, MessagesSnapshotEvent,
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent,
    TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent,
    StateSnapshotEvent,
)

from .responses_api import get_thread_response_store, get_current_agui_thread_id


logger = logging.getLogger(__name__)

# Tools that are frontend-only (handled by CopilotKit, not backend)
# These tools trigger REST API calls from the frontend, not SSE streaming
FRONTEND_ONLY_TOOLS = {
    "filter_dashboard",
    "setThemeColor",
    "display_flight_list",
    "display_flight_detail",
    "display_historical_chart",
    # REST API data fetching actions (kept for backwards compat if any remain)
    "fetch_flight_details",
    "reload_all_flights",
    # NOTE: fetch_flights is now a BACKEND tool that updates activeFilter state
    # The frontend reacts to state.activeFilter changes and fetches via REST
}

# Frontend-only state fields that should be preserved from the incoming request
# These fields are set by frontend actions (like filter_dashboard) and should NOT
# be overwritten by the agent's state
# Note: activeFilter is NOT here - it's now set by backend fetch_flights tool
FRONTEND_ONLY_STATE_FIELDS = {
    "selectedRoute",
}


class DeduplicatingOrchestrator(Orchestrator):
    """Wraps DefaultOrchestrator to filter duplicate tool call events.
    
    The v2 Responses API can stream back tool calls from conversation history,
    causing the AG-UI event bridge to emit duplicate TOOL_CALL_START events.
    This orchestrator filters those duplicates at the event level.
    
    It also filters message history when continuing a conversation to prevent
    KeyError on call_id_to_id mapping (tool calls from previous turns aren't known).
    
    It also tracks text message lifecycle to ensure proper START/END pairing.
    
    Additionally, it extracts state (flights, historicalData) from tool call results
    and emits StateSnapshotEvent to sync with the frontend.
    """
    
    def __init__(self) -> None:
        self._inner = DefaultOrchestrator()
    
    def can_handle(self, context: ExecutionContext) -> bool:
        """Delegate to inner orchestrator."""
        return self._inner.can_handle(context)
    
    def _filter_frontend_tool_calls(self, context: ExecutionContext) -> None:
        """Filter messages to remove frontend-only tool calls and their results.
        
        Frontend-only tools (like filter_dashboard) are handled by CopilotKit locally
        and should NEVER be sent to Azure. This method removes:
        - Frontend tool calls from assistant messages (reconstructs message without them)
        - Tool result messages for frontend-only tools
        
        IMPORTANT: When an assistant message contains MIXED tool calls (both frontend
        and backend), we RECONSTRUCT the message to keep only the backend tool calls.
        This preserves conversation context for the LLM while avoiding Azure rejection.
        
        This is called UNCONDITIONALLY on every request because CopilotKit always
        sends the full conversation history, and Azure will reject messages containing
        tool calls it didn't initiate.
        """
        messages = context.messages
        if not messages:
            return
        
        original_count = len(messages)
        filtered = []
        
        # First pass: identify call_ids for frontend-only tools
        frontend_tool_call_ids: set[str] = set()
        
        for msg in messages:
            role = getattr(msg, 'role', None)
            role_value = role.value if hasattr(role, 'value') else str(role) if role else 'unknown'
            
            if role_value.lower() == 'assistant':
                msg_contents = getattr(msg, 'contents', None) or getattr(msg, 'content', None)
                if msg_contents:
                    contents = msg_contents if isinstance(msg_contents, list) else [msg_contents]
                    for c in contents:
                        if isinstance(c, FunctionCallContent):
                            tool_name = getattr(c, 'name', None)
                            call_id = getattr(c, 'call_id', None)
                            if tool_name in FRONTEND_ONLY_TOOLS and call_id:
                                frontend_tool_call_ids.add(call_id)
                                logger.debug("[DeduplicatingOrchestrator] Found frontend tool call: %s (id=%s)", tool_name, call_id[:12] if call_id else 'none')
        
        if not frontend_tool_call_ids:
            # No frontend tool calls found, nothing to filter
            return
        
        logger.debug("[DeduplicatingOrchestrator] Filtering %d frontend tool call IDs from %d messages", 
                    len(frontend_tool_call_ids), original_count)
        
        # Second pass: filter/reconstruct messages
        for i, msg in enumerate(messages):
            role = getattr(msg, 'role', None)
            role_value = role.value if hasattr(role, 'value') else str(role) if role else 'unknown'
            msg_contents = getattr(msg, 'contents', None) or getattr(msg, 'content', None)
            
            # Always keep user messages
            if role_value.lower() == 'user':
                filtered.append(msg)
                continue
            
            # Check tool result messages - filter if it's for a frontend tool
            if role_value.lower() == 'tool':
                if msg_contents:
                    contents = msg_contents if isinstance(msg_contents, list) else [msg_contents]
                    is_frontend_result = False
                    for c in contents:
                        call_id = getattr(c, 'call_id', None)
                        if call_id and call_id in frontend_tool_call_ids:
                            is_frontend_result = True
                            break
                    if is_frontend_result:
                        logger.debug("[DeduplicatingOrchestrator] Filtering tool result for frontend tool (msg %d)", i)
                        continue
                filtered.append(msg)
                continue
            
            # Check assistant messages - reconstruct without frontend tool calls
            if role_value.lower() == 'assistant':
                if msg_contents:
                    contents = msg_contents if isinstance(msg_contents, list) else [msg_contents]
                    
                    # Check if this message has any frontend tool calls
                    has_frontend = False
                    has_backend = False
                    for c in contents:
                        if isinstance(c, FunctionCallContent):
                            call_id = getattr(c, 'call_id', None)
                            if call_id and call_id in frontend_tool_call_ids:
                                has_frontend = True
                            else:
                                has_backend = True
                    
                    if has_frontend:
                        if not has_backend:
                            # Only frontend tools - filter entire message
                            logger.debug("[DeduplicatingOrchestrator] Filtering assistant msg with only frontend tools (msg %d)", i)
                            continue
                        else:
                            # Mixed tools - reconstruct without frontend tool calls
                            new_contents = [c for c in contents 
                                          if not (isinstance(c, FunctionCallContent) 
                                                 and getattr(c, 'call_id', None) in frontend_tool_call_ids)]
                            
                            if new_contents:
                                # Update the message contents in place
                                if hasattr(msg, 'contents'):
                                    msg.contents = new_contents
                                elif hasattr(msg, 'content'):
                                    msg.content = new_contents
                                logger.debug("[DeduplicatingOrchestrator] Reconstructed assistant msg %d: removed %d frontend tools, kept %d items", 
                                           i, len(contents) - len(new_contents), len(new_contents))
                            else:
                                # All contents were frontend tools
                                logger.debug("[DeduplicatingOrchestrator] Filtering assistant msg - all contents were frontend tools (msg %d)", i)
                                continue
                
                filtered.append(msg)
                continue
            
            # Keep other message types (system, etc.)
            filtered.append(msg)
        
        if len(filtered) != original_count:
            context._messages = filtered
            logger.info("[DeduplicatingOrchestrator] Filtered frontend tool calls: %d -> %d messages", 
                       original_count, len(filtered))
    
    def _filter_messages_for_fresh_start(
        self, 
        context: ExecutionContext, 
        agui_thread_id: str | None,
        thread_response_store: dict[str, str]
    ) -> None:
        """Filter messages to remove ALL tool calls from previous invocations for fresh starts.
        
        This is more aggressive than _filter_frontend_tool_calls - it removes ALL tool
        calls when starting a fresh conversation (no stored response_id).
        
        The SDK fails with KeyError because it doesn't have call_id_to_id mappings
        for tool calls it didn't initiate in this session.
        """
        # Only filter for fresh starts (no stored response_id)
        if agui_thread_id and agui_thread_id in thread_response_store:
            # Continuing a conversation - the ResponsesApiThreadMiddleware handles this
            return
        
        # Force load messages by accessing the property
        messages = context.messages
        if not messages:
            return
        
        original_count = len(messages)
        filtered = []
        
        logger.debug("[DeduplicatingOrchestrator] Filtering messages for fresh start: %d messages", original_count)
        
        for i, msg in enumerate(messages):
            # Get role - could be enum or string
            role = getattr(msg, 'role', None)
            role_value = role.value if hasattr(role, 'value') else str(role) if role else 'unknown'
            
            # Check for contents (AG-UI SDK uses 'contents' plural)
            msg_contents = getattr(msg, 'contents', None) or getattr(msg, 'content', None)
            
            # Log what we're seeing
            contents_info = []
            if msg_contents:
                for c in (msg_contents if isinstance(msg_contents, list) else [msg_contents]):
                    c_type = type(c).__name__
                    call_id = getattr(c, 'call_id', None)
                    if call_id:
                        contents_info.append(f"{c_type}(call_id={call_id[:12]}...)")
                    else:
                        contents_info.append(c_type)
            logger.debug("[DeduplicatingOrchestrator]   msg[%d]: role=%s, contents=%s", i, role_value, contents_info)
            
            # Always keep user messages
            if role_value.lower() == 'user':
                logger.debug("[DeduplicatingOrchestrator]     -> KEEP (user)")
                filtered.append(msg)
                continue
            
            # Skip tool messages entirely
            if role_value.lower() == 'tool':
                logger.debug("[DeduplicatingOrchestrator]     -> REMOVE (tool role)")
                continue
            
            # For assistant messages, check if they contain tool calls or results
            if role_value.lower() == 'assistant':
                has_tool_related = False
                if msg_contents:
                    contents = msg_contents if isinstance(msg_contents, list) else [msg_contents]
                    for c in contents:
                        if isinstance(c, (FunctionCallContent, FunctionResultContent)):
                            has_tool_related = True
                            break
                        # Also check for any content with call_id attribute
                        if hasattr(c, 'call_id') and c.call_id:
                            has_tool_related = True
                            break
                
                if has_tool_related:
                    logger.debug("[DeduplicatingOrchestrator]     -> REMOVE (assistant with tool call/result)")
                    continue
                
                # Keep pure text assistant messages
                logger.debug("[DeduplicatingOrchestrator]     -> KEEP (pure text assistant)")
                filtered.append(msg)
                continue
            
            # Keep other message types (system, etc.)
            logger.debug("[DeduplicatingOrchestrator]     -> KEEP (other role: %s)", role_value)
            filtered.append(msg)
        
        if len(filtered) != original_count:
            # Update context._messages directly (bypassing the property)
            context._messages = filtered
            logger.debug("[DeduplicatingOrchestrator] Filtered messages: %d -> %d", original_count, len(filtered))
    
    def _is_frontend_tool_result_only(self, context: ExecutionContext) -> bool:
        """Check if this request is just a tool result for a frontend-only tool.
        
        When CopilotKit handles a frontend action (like filter_dashboard), it sends
        the tool result back to the backend. We should NOT invoke the LLM again in
        this case - the frontend already handled it and the conversation turn is complete.
        
        We detect this by checking if the last message is a TOOL message (FunctionResultContent)
        for a frontend-only tool.
        """
        messages = context.messages
        if not messages:
            return False
        
        # Get the last message
        last_msg = messages[-1]
        role = getattr(last_msg, 'role', None)
        role_value = role.value if hasattr(role, 'value') else str(role) if role else 'unknown'
        
        # If last message is not a tool result, not a frontend tool result
        if role_value.lower() != 'tool':
            return False
        
        # Check if it's a result for a frontend-only tool
        msg_contents = getattr(last_msg, 'contents', None) or getattr(last_msg, 'content', None)
        if not msg_contents:
            return False
        
        contents = msg_contents if isinstance(msg_contents, list) else [msg_contents]
        for c in contents:
            if isinstance(c, FunctionResultContent):
                # Check the call_id - we need to find the corresponding tool call
                call_id = getattr(c, 'call_id', None)
                if call_id:
                    # Look for the assistant message with this call_id
                    for msg in messages:
                        msg_role = getattr(msg, 'role', None)
                        msg_role_value = msg_role.value if hasattr(msg_role, 'value') else str(msg_role) if msg_role else 'unknown'
                        if msg_role_value.lower() == 'assistant':
                            msg_contents2 = getattr(msg, 'contents', None) or getattr(msg, 'content', None)
                            if msg_contents2:
                                contents2 = msg_contents2 if isinstance(msg_contents2, list) else [msg_contents2]
                                for c2 in contents2:
                                    if isinstance(c2, FunctionCallContent):
                                        if getattr(c2, 'call_id', None) == call_id:
                                            tool_name = getattr(c2, 'name', None)
                                            if tool_name in FRONTEND_ONLY_TOOLS:
                                                logger.debug("[DeduplicatingOrchestrator] Last message is result for frontend tool: %s", tool_name)
                                                return True
        
        return False
    
    async def run(self, context: ExecutionContext):
        """Run the inner orchestrator and filter duplicate tool call events."""
        # Get shared state from responses_api module
        thread_response_store = get_thread_response_store()
        current_agui_thread_id = get_current_agui_thread_id()
        
        # Check if we're continuing a conversation - if so, filter messages
        # to only send new ones (server has the history via response_id chaining)
        agui_thread_id = context.thread_id
        
        # Set the thread_id ContextVar so the middleware can access it
        token = current_agui_thread_id.set(agui_thread_id)
        
        try:
            # IMPORTANT: Check if this is just a frontend tool result (e.g., filter_dashboard).
            # If so, we should NOT invoke the LLM again - CopilotKit already handled the action
            # and the conversation turn is complete. Just emit completion events and return.
            if self._is_frontend_tool_result_only(context):
                logger.info("[DeduplicatingOrchestrator] Frontend tool result detected - completing run without LLM invocation")
                
                # CRITICAL: Clear the stored response_id for this thread.
                # Azure's Responses API is waiting for this tool result, but we're not sending it.
                # If we don't clear the response_id, the next request will try to continue
                # from Azure's "stuck" state and fail with "No tool output found".
                if agui_thread_id and agui_thread_id in thread_response_store:
                    logger.info("[DeduplicatingOrchestrator] Clearing response_id for thread %s to reset Azure state", agui_thread_id)
                    del thread_response_store[agui_thread_id]
                
                # Emit minimal events to complete the AG-UI protocol properly
                yield RunStartedEvent(thread_id=agui_thread_id, run_id="frontend-action-complete")
                # Preserve the current state from the incoming request
                incoming_state = context.input_data.get("state", {})
                if incoming_state:
                    yield StateSnapshotEvent(snapshot=incoming_state)
                yield RunFinishedEvent(thread_id=agui_thread_id, run_id="frontend-action-complete")
                return
            
            # Log thread state at debug level
            logger.debug("[DeduplicatingOrchestrator] Thread ID: %s, in store: %s", agui_thread_id, agui_thread_id in thread_response_store)
            
            # ALWAYS filter out frontend-only tool calls from the message history.
            # These tools (like filter_dashboard) are handled by CopilotKit locally
            # and Azure will reject messages containing tool calls it didn't initiate.
            self._filter_frontend_tool_calls(context)
            
            # Check if we're continuing a conversation (have stored response_id)
            is_continuation = agui_thread_id and agui_thread_id in thread_response_store
            
            # For fresh starts, filter out ALL old tool calls/results (not just frontend ones)
            # This prevents KeyError on call_id_to_id when the SDK tries to process messages
            # that contain tool calls it doesn't have mappings for
            if not is_continuation:
                self._filter_messages_for_fresh_start(context, agui_thread_id, thread_response_store)
            
            if is_continuation:
                logger.debug("[DeduplicatingOrchestrator] CONTINUING conversation - will send tool result to Azure")
            else:
                logger.debug("[DeduplicatingOrchestrator] NEW conversation")
            
            seen_tool_call_ids: set[str] = set()
            completed_tool_call_ids: set[str] = set()
            
            # Track tool call names for each ID (so we know which tools completed)
            tool_call_names: dict[str, str] = {}
            
            # Track if a "command" tool was called (fetch_flights, clear_filter)
            # These tools update the dashboard - suppress text responses after them
            command_tool_called: bool = False
            COMMAND_TOOLS = {"fetch_flights", "clear_filter"}
            
            # Extracted state from tool results - will be emitted as StateSnapshotEvent
            extracted_state: dict = {}
            
            # Track the last known good state from inner orchestrator
            # This preserves all fields (historicalData, etc.) that we may not extract ourselves
            last_inner_state: dict = {}
            
            # Capture frontend state from the incoming request
            # This preserves frontend-only fields like activeFilter and selectedRoute
            # that should not be overwritten by the agent's state
            frontend_state: dict = {}
            incoming_state = context.input_data.get("state", {})
            logger.info("[DeduplicatingOrchestrator] Incoming state keys: %s", list(incoming_state.keys()) if incoming_state else "None")
            if incoming_state:
                active_filter_in_state = incoming_state.get("activeFilter")
                logger.info("[DeduplicatingOrchestrator] activeFilter in incoming state: %s", active_filter_in_state)
                
                for field in FRONTEND_ONLY_STATE_FIELDS:
                    if field in incoming_state and incoming_state[field] is not None:
                        frontend_state[field] = incoming_state[field]
                        logger.debug("[DeduplicatingOrchestrator] Preserving frontend field '%s': %s", field, incoming_state[field])
                
                # Set the current active filter ContextVar for tools to access
                # This allows analyze_flights to automatically use the current filter
                active_filter = incoming_state.get("activeFilter")
                if active_filter:
                    # Clean up __KEEP__ sentinel values - they should be treated as None
                    cleaned_filter = {
                        k: (None if v == "__KEEP__" else v)
                        for k, v in active_filter.items()
                    }
                    from agents.logistics_agent import current_active_filter
                    current_active_filter.set(cleaned_filter)
                    logger.info("[DeduplicatingOrchestrator] Set current_active_filter ContextVar: %s", cleaned_filter)
                else:
                    logger.warning("[DeduplicatingOrchestrator] No activeFilter in incoming state - analyze_flights won't have context")
            
            # Track text message lifecycle to ensure proper START/END pairing
            # Buffer START events until we see content - this filters out "tool-only response" placeholders
            pending_start_events: dict[str, TextMessageStartEvent] = {}  # message_id -> event
            active_text_message_ids: set[str] = set()  # Messages that have been emitted (had content)
            
            async for event in self._inner.run(context):
                # Log all events for debugging
                event_type = type(event).__name__
                logger.debug("[DeduplicatingOrchestrator] Event: %s", event_type)
                
                # --- StateSnapshotEvent - BUFFER instead of emitting immediately ---
                # This prevents flashing when inner orchestrator emits state BEFORE
                # we've extracted activeFilter from tool results
                if isinstance(event, StateSnapshotEvent):
                    snapshot = event.snapshot or {}
                    flights_count = len(snapshot.get('flights', []))
                    historical_count = len(snapshot.get('historicalData', []))
                    logger.debug("[DeduplicatingOrchestrator] StateSnapshotEvent from inner (buffering): keys=%s, flights=%d, historical=%d",
                               list(snapshot.keys()), flights_count, historical_count)
                    
                    # ALWAYS preserve the inner state - it may have fields we don't extract
                    # Only update fields that have actual data (don't overwrite with empty)
                    for key, value in snapshot.items():
                        if value is not None and value != [] and value != {}:
                            last_inner_state[key] = value
                        elif key not in last_inner_state:
                            # Set to empty if we haven't seen this key before
                            last_inner_state[key] = value
                    
                    # DON'T emit here - buffer and emit once at RunFinished
                    # This ensures we have all extracted state (activeFilter) before emitting
                    continue
                
                # --- Tool call deduplication ---
                elif isinstance(event, ToolCallStartEvent):
                    tool_call_id = event.tool_call_id
                    tool_name = event.tool_call_name
                    
                    logger.debug("[DeduplicatingOrchestrator] ToolCallStart: name=%s, id=%s", tool_name, tool_call_id[:12] if tool_call_id else "None")
                    
                    # Check for duplicate first (applies to ALL tools, frontend and backend)
                    if tool_call_id in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate ToolCallStartEvent: %s (%s)", tool_call_id, tool_name)
                        continue
                    
                    # Track this tool call
                    seen_tool_call_ids.add(tool_call_id)
                    tool_call_names[tool_call_id] = tool_name
                    
                    # Mark command tools immediately - suppress text from this point
                    if tool_name in COMMAND_TOOLS:
                        command_tool_called = True
                        logger.info("[DeduplicatingOrchestrator] Command tool started: %s (suppressing text)", tool_name)
                    
                    # Log ALL tool calls at INFO level to see what's happening
                    if tool_name in FRONTEND_ONLY_TOOLS:
                        logger.debug("[DeduplicatingOrchestrator] -> FRONTEND tool: %s", tool_name)
                    else:
                        logger.debug("[DeduplicatingOrchestrator] -> BACKEND tool: %s", tool_name)
                
                elif isinstance(event, ToolCallArgsEvent):
                    tool_call_id = event.tool_call_id
                    # Only emit args for tool calls we've started
                    if tool_call_id not in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering ToolCallArgsEvent for unknown call: %s", tool_call_id)
                        continue
                    # Don't emit args for completed tool calls
                    if tool_call_id in completed_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering ToolCallArgsEvent for completed call: %s", tool_call_id)
                        continue
                    
                    # Extract state from frontend tool calls
                    # When filter_dashboard is called, capture the filter args so we can preserve them
                    tool_name = tool_call_names.get(tool_call_id)
                    if tool_name == "filter_dashboard" and event.delta:
                        # Accumulate args for this tool call
                        if not hasattr(self, '_tool_args_buffer'):
                            self._tool_args_buffer = {}
                        if tool_call_id not in self._tool_args_buffer:
                            self._tool_args_buffer[tool_call_id] = ""
                        self._tool_args_buffer[tool_call_id] += event.delta
                    # Note: Don't continue here - we still need to yield the event
                
                elif isinstance(event, ToolCallEndEvent):
                    tool_call_id = event.tool_call_id
                    # Skip if we haven't seen this tool call start
                    if tool_call_id not in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering ToolCallEndEvent for unknown call: %s", tool_call_id)
                        continue
                    if tool_call_id in completed_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate ToolCallEndEvent: %s", tool_call_id)
                        continue
                    completed_tool_call_ids.add(tool_call_id)
                    logger.debug("[DeduplicatingOrchestrator] Emitting ToolCallEndEvent: %s", tool_call_id)
                    
                    # Extract filter state from filter_dashboard tool call when it ends
                    tool_name = tool_call_names.get(tool_call_id)
                    if tool_name == "filter_dashboard" and hasattr(self, '_tool_args_buffer'):
                        args_str = self._tool_args_buffer.get(tool_call_id, "")
                        if args_str:
                            try:
                                args = json.loads(args_str)
                                logger.debug("[DeduplicatingOrchestrator] Extracted filter_dashboard args: %s", args)
                                
                                # Normalize route format like the frontend does
                                route = args.get("route")
                                if route:
                                    route = route.upper().replace("-", " → ").replace(" TO ", " → ")
                                
                                utilization_type = args.get("utilizationType")
                                
                                # Build the filter object
                                has_filter = route or (utilization_type and utilization_type != "all")
                                if has_filter:
                                    extracted_state["activeFilter"] = {
                                        "route": route,
                                        "utilizationType": utilization_type,
                                    }
                                    extracted_state["selectedRoute"] = route
                                    logger.debug("[DeduplicatingOrchestrator] Set extracted activeFilter: %s", extracted_state["activeFilter"])
                                else:
                                    # Clear filter
                                    extracted_state["activeFilter"] = None
                                    extracted_state["selectedRoute"] = None
                                
                                # Emit the ToolCallEndEvent first
                                yield event
                                
                                # Emit a StateSnapshotEvent with the updated filter
                                # This ensures the frontend gets the filter before the run finishes
                                merged = {**last_inner_state, **extracted_state, **frontend_state}
                                logger.debug("[DeduplicatingOrchestrator] Emitting StateSnapshotEvent after filter_dashboard: activeFilter=%s", merged.get('activeFilter'))
                                yield StateSnapshotEvent(snapshot=merged)
                                continue  # Skip the default yield since we already yielded the event
                                
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.warning("[DeduplicatingOrchestrator] Failed to parse filter_dashboard args: %s", e)
                
                elif isinstance(event, ToolCallResultEvent):
                    tool_call_id = event.tool_call_id
                    # Results should only come after the call ends, but filter duplicates anyway
                    if tool_call_id not in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering ToolCallResultEvent for unknown call: %s", tool_call_id)
                        continue
                    
                    # Extract state from tool results
                    tool_name = tool_call_names.get(tool_call_id, "unknown")
                    result = event.content
                    
                    logger.debug("[DeduplicatingOrchestrator] ToolCallResultEvent: tool=%s, content_type=%s, content_preview=%s",
                               tool_name, type(result).__name__, str(result)[:200])
                    
                    # Try to parse JSON if it's a string
                    if isinstance(result, str):
                        try:
                            result = json.loads(result)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    # Extract flights from tool results
                    if isinstance(result, dict):
                        if "flights" in result:
                            extracted_state["flights"] = result["flights"]
                            logger.debug("[DeduplicatingOrchestrator] Extracted %d flights from %s",
                                       len(result["flights"]), tool_name)
                        if "historical_data" in result:
                            extracted_state["historicalData"] = result["historical_data"]
                            logger.debug("[DeduplicatingOrchestrator] Extracted %d historical points from %s",
                                       len(result["historical_data"]), tool_name)
                        if "selectedFlight" in result:
                            extracted_state["selectedFlight"] = result["selectedFlight"]
                            logger.debug("[DeduplicatingOrchestrator] Extracted selectedFlight from %s", tool_name)
                        # Extract activeFilter from fetch_flights/clear_filter tool results
                        if "activeFilter" in result:
                            # Clean up __KEEP__ sentinel values - they should be treated as None
                            raw_filter = result["activeFilter"]
                            cleaned_filter = {
                                k: (None if v == "__KEEP__" else v)
                                for k, v in raw_filter.items()
                            }
                            extracted_state["activeFilter"] = cleaned_filter
                            command_tool_called = True  # Suppress text responses
                            logger.info("[DeduplicatingOrchestrator] Extracted activeFilter from %s: %s (command_tool_called=True)", 
                                       tool_name, cleaned_filter)
                            
                            # Also update the ContextVar so subsequent tools (like analyze_flights)
                            # can access the updated filter within the same request
                            from agents.logistics_agent import current_active_filter
                            current_active_filter.set(cleaned_filter)
                            logger.debug("[DeduplicatingOrchestrator] Updated current_active_filter ContextVar: %s", cleaned_filter)
                            
                            # 🚀 EMIT StateSnapshotEvent IMMEDIATELY for activeFilter
                            # Yield the ToolCallResultEvent FIRST so the tool is marked complete,
                            # THEN emit the state snapshot so frontend can start REST fetch
                            yield event  # ToolCallResultEvent - marks tool complete
                            
                            merged = {**last_inner_state, **extracted_state, **frontend_state}
                            logger.info("[DeduplicatingOrchestrator] Emitting EARLY StateSnapshotEvent for activeFilter: %s", cleaned_filter)
                            yield StateSnapshotEvent(snapshot=merged)
                            continue  # Skip the default yield since we already yielded the event
                
                # --- Text message lifecycle tracking (with buffering) ---
                elif isinstance(event, TextMessageStartEvent):
                    # Suppress text messages after command tools (fetch_flights, clear_filter)
                    if command_tool_called:
                        logger.info("[DeduplicatingOrchestrator] SUPPRESSING TextMessageStart after command tool: %s", event.message_id)
                        continue
                    message_id = event.message_id
                    if message_id in pending_start_events or message_id in active_text_message_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate TextMessageStartEvent: %s", message_id)
                        continue
                    # Buffer the START event - only emit when we see content
                    pending_start_events[message_id] = event
                    logger.debug("[DeduplicatingOrchestrator] Buffering TextMessageStart: %s", message_id)
                    continue  # Don't yield yet
                
                elif isinstance(event, TextMessageContentEvent):
                    # Suppress text messages after command tools
                    if command_tool_called:
                        logger.info("[DeduplicatingOrchestrator] SUPPRESSING TextMessageContent after command tool: %s", event.delta[:50] if event.delta else "(empty)")
                        continue
                    message_id = event.message_id
                    # If we have a pending start for this message, emit it now
                    if message_id in pending_start_events:
                        start_event = pending_start_events.pop(message_id)
                        active_text_message_ids.add(message_id)
                        logger.debug("[DeduplicatingOrchestrator] Emitting buffered TextMessageStart: %s", message_id)
                        yield start_event
                    # Only emit content for messages we've started
                    if message_id not in active_text_message_ids:
                        logger.warning("[DeduplicatingOrchestrator] TextMessageContent for unknown message: %s, skipping", message_id)
                        continue
                
                elif isinstance(event, TextMessageEndEvent):
                    message_id = event.message_id
                    # If message is still pending (never got content), just drop both start and end
                    if message_id in pending_start_events:
                        pending_start_events.pop(message_id)
                        logger.debug("[DeduplicatingOrchestrator] Dropping phantom message (no content): %s", message_id)
                        continue
                    if message_id not in active_text_message_ids:
                        logger.warning("[DeduplicatingOrchestrator] TextMessageEnd for unknown message: %s, skipping", message_id)
                        continue
                    active_text_message_ids.discard(message_id)
                    logger.debug("[DeduplicatingOrchestrator] Closing TextMessage: %s", message_id)
                
                elif isinstance(event, RunFinishedEvent):
                    # Close any messages that are active (received content but not closed)
                    if active_text_message_ids:
                        logger.warning("[DeduplicatingOrchestrator] Found %d unclosed text messages, closing them", 
                                      len(active_text_message_ids))
                        for msg_id in list(active_text_message_ids):
                            logger.debug("[DeduplicatingOrchestrator] Emitting TextMessageEndEvent for: %s", msg_id)
                            yield TextMessageEndEvent(message_id=msg_id)
                        active_text_message_ids.clear()
                    
                    # Drop any pending (phantom) messages that never got content
                    if pending_start_events:
                        logger.debug("[DeduplicatingOrchestrator] Dropping %d phantom text messages", len(pending_start_events))
                        pending_start_events.clear()
                    
                    # Emit final StateSnapshotEvent with all buffered state merged
                    # Merge order: inner state < extracted state < frontend state
                    merged = {**last_inner_state, **extracted_state, **frontend_state}
                    logger.info("[DeduplicatingOrchestrator] RunFinished - emitting final state: flights=%d, historical=%d, activeFilter=%s",
                               len(merged.get('flights', [])),
                               len(merged.get('historicalData', [])),
                               merged.get('activeFilter'))
                    yield StateSnapshotEvent(snapshot=merged)
                
                yield event
        finally:
            # Only reset the thread_id ContextVar here
            # DON'T reset ended_with_frontend_tool - the middleware needs to read it
            # after the generator completes. It will be reset at the start of the next request.
            current_agui_thread_id.reset(token)
