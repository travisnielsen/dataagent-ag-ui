"""
Custom Orchestrators for AG-UI Protocol

This module provides custom orchestrators that wrap the default AG-UI orchestrators
to handle v2 Responses API compatibility issues.
"""

from __future__ import annotations

import logging

from agent_framework_ag_ui._orchestrators import DefaultOrchestrator, Orchestrator, ExecutionContext
from ag_ui.core import (
    ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent, ToolCallResultEvent,
    TextMessageStartEvent, TextMessageContentEvent, TextMessageEndEvent, RunFinishedEvent,
)

from .responses_api import get_thread_response_store, get_current_agui_thread_id


logger = logging.getLogger(__name__)


class DeduplicatingOrchestrator(Orchestrator):
    """Wraps DefaultOrchestrator to filter duplicate tool call events.
    
    The v2 Responses API can stream back tool calls from conversation history,
    causing the AG-UI event bridge to emit duplicate TOOL_CALL_START events.
    This orchestrator filters those duplicates at the event level.
    
    It also filters message history when continuing a conversation to prevent
    KeyError on call_id_to_id mapping (tool calls from previous turns aren't known).
    
    It also tracks text message lifecycle to ensure proper START/END pairing.
    """
    
    def __init__(self) -> None:
        self._inner = DefaultOrchestrator()
    
    def can_handle(self, context: ExecutionContext) -> bool:
        """Delegate to inner orchestrator."""
        return self._inner.can_handle(context)
    
    async def run(self, context: ExecutionContext):
        """Run the inner orchestrator and filter duplicate tool call events."""
        # Get shared state from responses_api module
        thread_response_store = get_thread_response_store()
        current_agui_thread_id = get_current_agui_thread_id()
        
        # Check if we're continuing a conversation - if so, filter messages
        # to only send new ones (server has the history via response_id chaining)
        agui_thread_id = context.thread_id
        
        # Set the ContextVar so the middleware can access the thread_id
        token = current_agui_thread_id.set(agui_thread_id)
        
        try:
            # Log thread state at debug level
            logger.debug("[DeduplicatingOrchestrator] Thread ID: %s, in store: %s", agui_thread_id, agui_thread_id in thread_response_store)
            
            if agui_thread_id and agui_thread_id in thread_response_store:
                logger.debug("[DeduplicatingOrchestrator] CONTINUING conversation")
            else:
                logger.debug("[DeduplicatingOrchestrator] NEW conversation")
            
            seen_tool_call_ids: set[str] = set()
            completed_tool_call_ids: set[str] = set()
            
            # Track text message lifecycle to ensure proper START/END pairing
            # Buffer START events until we see content - this filters out "tool-only response" placeholders
            pending_start_events: dict[str, TextMessageStartEvent] = {}  # message_id -> event
            active_text_message_ids: set[str] = set()  # Messages that have been emitted (had content)
            
            async for event in self._inner.run(context):
                # --- Tool call deduplication ---
                if isinstance(event, ToolCallStartEvent):
                    tool_call_id = event.tool_call_id
                    if tool_call_id in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate ToolCallStartEvent: %s", tool_call_id)
                        continue
                    seen_tool_call_ids.add(tool_call_id)
                    logger.debug("[DeduplicatingOrchestrator] Emitting ToolCallStartEvent: %s (%s)", tool_call_id, event.tool_call_name)
                
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
                
                elif isinstance(event, ToolCallEndEvent):
                    tool_call_id = event.tool_call_id
                    if tool_call_id in completed_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering duplicate ToolCallEndEvent: %s", tool_call_id)
                        continue
                    completed_tool_call_ids.add(tool_call_id)
                    logger.debug("[DeduplicatingOrchestrator] Emitting ToolCallEndEvent: %s", tool_call_id)
                
                elif isinstance(event, ToolCallResultEvent):
                    tool_call_id = event.tool_call_id
                    # Results should only come after the call ends, but filter duplicates anyway
                    if tool_call_id not in seen_tool_call_ids:
                        logger.debug("[DeduplicatingOrchestrator] Filtering ToolCallResultEvent for unknown call: %s", tool_call_id)
                        continue
                
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
                    
                    logger.debug("[DeduplicatingOrchestrator] RunFinished")
                
                yield event
        finally:
            # Reset the ContextVar when the generator completes or errors
            current_agui_thread_id.reset(token)
