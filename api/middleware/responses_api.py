"""
Responses API Thread Middleware

This module provides middleware for managing Azure v2 Responses API conversation continuity.
It maps AG-UI client thread IDs to Azure response_id chains.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Callable, Awaitable
from collections.abc import AsyncIterable
import logging

from agent_framework._types import ChatResponse, ChatResponseUpdate, FunctionCallContent, Role
from agent_framework._middleware import ChatMiddleware, ChatContext


logger = logging.getLogger(__name__)


# Thread mapping store: maps AG-UI thread_id (client UUID) to Azure response_id
# This persists the response ID across requests so we can reuse Azure server-side state
_thread_response_store: dict[str, str] = {}

# ContextVar to pass AG-UI thread_id from orchestrator to middleware
# This allows the middleware to access the thread_id without modifying kwargs
_current_agui_thread_id: ContextVar[str | None] = ContextVar("current_agui_thread_id", default=None)


def get_thread_response_store() -> dict[str, str]:
    """Get the thread-to-response-id mapping store."""
    return _thread_response_store


def get_current_agui_thread_id() -> ContextVar[str | None]:
    """Get the ContextVar for the current AG-UI thread ID."""
    return _current_agui_thread_id


class ResponsesApiThreadMiddleware(ChatMiddleware):
    """Chat middleware that manages response ID mapping for v2 Responses API.
    
    The Responses API uses response IDs (resp_*) for conversation continuity.
    AG-UI sends a client-generated thread_id (UUID), but we need to pass the
    previous response_id as the conversation_id to continue conversations.
    
    This middleware:
    1. Before request: Gets AG-UI thread_id from kwargs metadata and sets conversation_id to stored response_id
    2. After response: Stores the new response_id for the next request
    """
    
    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],  # noqa: A002 - required by base class
    ) -> None:
        """Process the chat request, managing response ID mapping."""
        # Get the AG-UI thread_id from ContextVar (set by DeduplicatingOrchestrator)
        agui_thread_id = _current_agui_thread_id.get()
        
        logger.info("[ResponsesApiThreadMiddleware] AG-UI thread_id from ContextVar: %s", agui_thread_id)
        
        # Check if we have a stored response_id for this AG-UI thread
        if agui_thread_id and agui_thread_id in _thread_response_store:
            stored_response_id = _thread_response_store[agui_thread_id]
            logger.info("[ResponsesApiThreadMiddleware] Using stored response_id: %s for AG-UI thread: %s", stored_response_id, agui_thread_id)
            # Set the conversation_id to the stored response_id
            context.chat_options.conversation_id = stored_response_id
            
            # Filter messages to only send new ones - server has the history via conversation_id
            # This prevents KeyError on call_id_to_id for tool calls from previous turns
            self._filter_messages_for_api(context)
        elif agui_thread_id:
            # First request for this thread - clear any existing conversation_id
            logger.info("[ResponsesApiThreadMiddleware] New conversation for AG-UI thread: %s", agui_thread_id)
            context.chat_options.conversation_id = None
        
        # Call the next middleware/handler
        await next(context)
        
        # For streaming responses, capture the response_id after the stream completes
        if context.is_streaming and context.result is not None:
            if hasattr(context.result, '__aiter__'):
                # Wrap only to capture response_id
                # Type narrow: we've verified it's an AsyncIterable via hasattr check
                context.result = self._capture_response_id(
                    context.result,  # type: ignore[arg-type]
                    agui_thread_id,
                )
        elif agui_thread_id and context.result:
            # For non-streaming, extract and store the response_id
            new_response_id = self._extract_response_id(context)
            if new_response_id and new_response_id.startswith(("resp_", "conv_")):
                _thread_response_store[agui_thread_id] = new_response_id
                logger.info("[ResponsesApiThreadMiddleware] Stored response_id: %s for AG-UI thread: %s", new_response_id, agui_thread_id)
    
    async def _capture_response_id(
        self,
        stream: AsyncIterable[ChatResponseUpdate],
        agui_thread_id: str | None,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Pass through stream unchanged, only capturing response_id at the end."""
        last_response_id: str | None = None
        
        async for update in stream:
            if update.response_id:
                last_response_id = update.response_id
            if update.conversation_id:
                last_response_id = update.conversation_id
            yield update
        
        # Store response_id after streaming completes
        if agui_thread_id and last_response_id:
            if last_response_id.startswith(("resp_", "conv_")):
                _thread_response_store[agui_thread_id] = last_response_id
                logger.info("[ResponsesApiThreadMiddleware] Stored response_id: %s for AG-UI thread: %s", last_response_id, agui_thread_id)
    
    def _extract_response_id(self, context: ChatContext) -> str | None:
        """Extract the response_id from the result."""
        result = context.result
        if result is None:
            return None
        
        # For non-streaming (ChatResponse)
        if isinstance(result, ChatResponse):
            return result.response_id or result.conversation_id
        
        return None
    
    def _filter_messages_for_api(self, context: ChatContext) -> None:
        """Filter messages when continuing a conversation.
        
        When we have a stored response_id, the server already has the conversation
        history. We only need to send new messages to avoid KeyError on call_id_to_id.
        
        New messages can be:
        - A new user message (user asking a follow-up question)
        - A tool result message (frontend tool returning results)
        
        We find the last "new input" (user or tool message) and send only from there.
        
        NOTE: This modifies context.messages (what gets sent to API) but NOT the
        orchestrator's input_data (which is used for MessagesSnapshotEvent).
        """
        messages = context.messages
        if not messages:
            return
        
        original_count = len(messages)
        
        # Find the last "new input" message - either user or tool (whichever is last)
        # This handles both:
        # - Normal continuation: [user, assistant, user] → send last user
        # - Frontend tool result: [user, assistant, tool] → send tool result only
        last_input_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            role = getattr(msg, 'role', None)
            # Tool results and new user messages are "new inputs" to continue the conversation
            if role == Role.USER or role == Role.TOOL:
                last_input_idx = i
                break
        
        if last_input_idx >= 0:
            # Only keep from the last input message onwards
            filtered = messages[last_input_idx:]
            # Replace the messages list in-place
            context.messages.clear()
            context.messages.extend(filtered)
            logger.info("[ResponsesApiThreadMiddleware] Filtered messages for API: %d -> %d (starting at %s message)",
                       original_count, len(context.messages), 
                       "tool" if getattr(filtered[0], 'role', None) == Role.TOOL else "user")


async def deduplicate_tool_calls(
    stream: AsyncIterable[ChatResponseUpdate],
    agui_thread_id: str | None,
) -> AsyncIterable[ChatResponseUpdate]:
    """Wrap a streaming response to deduplicate tool call events.
    
    The v2 Responses API can emit the same tool call multiple times in a response,
    which causes AG-UI to throw "TOOL_CALL_START already in progress" errors.
    
    This wrapper tracks seen tool call IDs and filters out duplicates while
    preserving all other update properties (especially finish_reason which is
    required for AG-UI to properly close text messages).
    
    NOTE: This function is currently unused - the DeduplicatingOrchestrator
    handles deduplication at the event level instead.
    """
    seen_tool_call_ids: set[str] = set()
    last_response_id: str | None = None
    
    async for update in stream:
        # Track the response_id for thread mapping
        if update.response_id:
            last_response_id = update.response_id
        if update.conversation_id:
            last_response_id = update.conversation_id
        
        # Filter out duplicate tool calls from contents
        if update.contents:
            filtered_contents = []
            has_duplicates = False
            
            for content in update.contents:
                if isinstance(content, FunctionCallContent):
                    call_id = content.call_id
                    if call_id and call_id in seen_tool_call_ids:
                        logger.debug("[Dedup] Filtering duplicate tool call: %s", call_id)
                        has_duplicates = True
                        continue
                    if call_id:
                        seen_tool_call_ids.add(call_id)
                filtered_contents.append(content)
            
            # Only modify the update if we actually filtered something
            if has_duplicates:
                # If no contents left but update has important metadata, still yield it
                # (finish_reason is critical for AG-UI to close text messages properly)
                if not filtered_contents and not update.finish_reason:
                    continue
                
                # Create new update with filtered contents
                update = ChatResponseUpdate(
                    role=update.role,
                    contents=filtered_contents if filtered_contents else None,
                    response_id=update.response_id,
                    conversation_id=update.conversation_id,
                    message_id=update.message_id,
                    model_id=update.model_id,
                    finish_reason=update.finish_reason,
                    raw_representation=update.raw_representation,
                    created_at=update.created_at,
                    author_name=update.author_name,
                    additional_properties=update.additional_properties,
                )
        
        yield update
    
    # After streaming completes, store the response_id for thread mapping
    if agui_thread_id and last_response_id:
        if last_response_id.startswith(("resp_", "conv_")):
            _thread_response_store[agui_thread_id] = last_response_id
            logger.info("[Dedup] Stored response_id: %s for AG-UI thread: %s", last_response_id, agui_thread_id)
