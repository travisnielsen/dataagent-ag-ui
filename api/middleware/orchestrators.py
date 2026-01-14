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
FRONTEND_ONLY_TOOLS = {
    "filter_dashboard",
    "setThemeColor",
    "display_flight_list",
    "display_flight_detail",
    "display_historical_chart",
}

# Frontend-only state fields that should be preserved from the incoming request
# These fields are set by frontend actions (like filter_dashboard) and should NOT
# be overwritten by the agent's state
FRONTEND_ONLY_STATE_FIELDS = {
    "activeFilter",
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
    
    def _filter_messages_for_fresh_start(
        self, 
        context: ExecutionContext, 
        agui_thread_id: str | None,
        thread_response_store: dict[str, str]
    ) -> None:
        """Filter messages to remove tool calls from previous frontend tool invocations.
        
        When a frontend-only tool (like filter_dashboard) is called, CopilotKit handles
        it locally and doesn't send a result back to Azure. On the next request,
        CopilotKit sends the full message history including that tool call.
        
        The SDK fails with KeyError because it doesn't have call_id_to_id mappings
        for tool calls it didn't initiate in this session.
        
        This method filters out:
        - Messages with role=TOOL (tool results)
        - Assistant messages containing FunctionCallContent or FunctionResultContent
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
            # Log thread state at debug level
            logger.debug("[DeduplicatingOrchestrator] Thread ID: %s, in store: %s", agui_thread_id, agui_thread_id in thread_response_store)
            
            # Check if we're continuing a conversation (have stored response_id)
            is_continuation = agui_thread_id and agui_thread_id in thread_response_store
            
            # For continuations with tool results, we let it through - Azure needs the tool result
            # For fresh starts, filter out old tool calls/results
            if not is_continuation:
                # Filter messages to remove tool calls/results from previous frontend tool invocations
                # This prevents KeyError on call_id_to_id when the SDK tries to process messages
                # that contain tool calls it doesn't have mappings for
                self._filter_messages_for_fresh_start(context, agui_thread_id, thread_response_store)
            
            if is_continuation:
                logger.debug("[DeduplicatingOrchestrator] CONTINUING conversation - will send tool result to Azure")
            else:
                logger.debug("[DeduplicatingOrchestrator] NEW conversation")
            
            seen_tool_call_ids: set[str] = set()
            completed_tool_call_ids: set[str] = set()
            
            # Track tool call names for each ID (so we know which tools completed)
            tool_call_names: dict[str, str] = {}
            
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
            if incoming_state:
                for field in FRONTEND_ONLY_STATE_FIELDS:
                    if field in incoming_state and incoming_state[field] is not None:
                        frontend_state[field] = incoming_state[field]
                        logger.debug("[DeduplicatingOrchestrator] Preserving frontend field '%s': %s", field, incoming_state[field])
            
            # Track text message lifecycle to ensure proper START/END pairing
            # Buffer START events until we see content - this filters out "tool-only response" placeholders
            pending_start_events: dict[str, TextMessageStartEvent] = {}  # message_id -> event
            active_text_message_ids: set[str] = set()  # Messages that have been emitted (had content)
            
            async for event in self._inner.run(context):
                # Log all events for debugging
                event_type = type(event).__name__
                logger.debug("[DeduplicatingOrchestrator] Event: %s", event_type)
                
                # --- StateSnapshotEvent - preserve and merge, then pass through ---
                if isinstance(event, StateSnapshotEvent):
                    snapshot = event.snapshot or {}
                    flights_count = len(snapshot.get('flights', []))
                    historical_count = len(snapshot.get('historicalData', []))
                    logger.debug("[DeduplicatingOrchestrator] StateSnapshotEvent from inner: keys=%s, flights=%d, historical=%d",
                               list(snapshot.keys()), flights_count, historical_count)
                    
                    # ALWAYS preserve the inner state - it may have fields we don't extract
                    # Only update fields that have actual data (don't overwrite with empty)
                    for key, value in snapshot.items():
                        if value is not None and value != [] and value != {}:
                            last_inner_state[key] = value
                        elif key not in last_inner_state:
                            # Set to empty if we haven't seen this key before
                            last_inner_state[key] = value
                    
                    # Merge order (later takes priority):
                    # 1. inner state (from agent)
                    # 2. extracted state (from tool results)
                    # 3. frontend state (from incoming request - highest priority for frontend-only fields)
                    merged = {**last_inner_state, **extracted_state, **frontend_state}
                    logger.debug("[DeduplicatingOrchestrator] Merged state emitting: flights=%d, historical=%d, activeFilter=%s",
                               len(merged.get('flights', [])),
                               len(merged.get('historicalData', [])),
                               merged.get('activeFilter'))
                    yield StateSnapshotEvent(snapshot=merged)
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
                
                # --- Text message lifecycle tracking (with buffering) ---
                elif isinstance(event, TextMessageStartEvent):
                    message_id = event.message_id
                    if message_id in pending_start_events or message_id in active_text_message_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate TextMessageStartEvent: %s", message_id)
                        continue
                    # Buffer the START event - only emit when we see content
                    pending_start_events[message_id] = event
                    logger.debug("[DeduplicatingOrchestrator] Buffering TextMessageStart: %s", message_id)
                    continue  # Don't yield yet
                
                elif isinstance(event, TextMessageContentEvent):
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
                    
                    # DON'T emit a separate final StateSnapshotEvent here!
                    # The inner orchestrator already emits StateSnapshotEvents with the full state,
                    # and we're preserving/merging those above. Emitting a partial extracted_state
                    # here was causing the state to be reset (missing historicalData, etc.)
                    logger.debug("[DeduplicatingOrchestrator] RunFinished - final state: flights=%d, historical=%d",
                                len(last_inner_state.get('flights', [])),
                                len(last_inner_state.get('historicalData', [])))
                
                yield event
        finally:
            # Only reset the thread_id ContextVar here
            # DON'T reset ended_with_frontend_tool - the middleware needs to read it
            # after the generator completes. It will be reset at the start of the next request.
            current_agui_thread_id.reset(token)
