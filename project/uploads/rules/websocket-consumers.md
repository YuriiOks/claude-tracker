---
paths:
  - "**/consumers*"
  - "**/channels/**"
  - "spa-frontend/src/utils/channels/**"
  - "spa-frontend/src/composables/useChannel*"
---

# WebSocket Consumer Patterns (Jupus AI Chat)

## AIChatConsumer Architecture (`app/ai/consumers.py`)

### Connection Flow
1. Authenticate user from scope
2. Verify session access: `session.org == user.org` (or superuser)
3. Join channel group: `ai_chat_session_{session_uuid}`
4. Send `CONNECTION_ESTABLISHED`

### Threading Model
- Main async event loop handles WebSocket I/O
- Streaming runs in **background thread** via `_stream_worker()`
- Thread sends events to channel group via `asyncio.run_coroutine_threadsafe()`
- `_cancel_event` threading.Event for abort support

### Message Types (Client -> Server)
- `send_message` — new user message (content + optional model)
- `reask_with_court_db` — re-stream with court DB enabled
- `cancel_stream` — set cancel event flag

### Event Types (Server -> Client)
- `session_state_change` — state transition (UPDATING_CONTEXT, SEARCHING_DOCUMENTS, REASONING, READY)
- `text_delta` — streaming token
- `text_chunk_end` — end of structured chunk
- `chunk` — structured data piece
- `verdict_context` — court DB results
- `message_complete` — final message (source of truth)
- `done` — stream finished
- `error` — error occurred

### ACM-Specific Events (New)
- `model_resolved` — confirms model for this request
- `model_fallback` — silent fallback occurred (auto mode)
- `model_error` — explicit model unavailable

### Event Routing
```python
_EVENT_TYPE_MAP = {
    "state_change": "session_state_change",
    # ... maps internal event names to WS message types
}
```

### Ownership Check Pattern (ACM-023)
```python
# Before processing send_message:
if session.started_by_user != self.scope["user"]:
    await self.send_error("Not session owner")
    return
```

### Session State Gating
Consumer checks session state before accepting new messages — prevents concurrent processing on the same session.

## Frontend WebSocket Patterns

### ChannelManager Singleton
`spa-frontend/src/utils/channels/ChannelManager.ts` manages multiple WS connections.

### useChannelSubscription Composable
`spa-frontend/src/composables/useChannelSubscription.ts` provides:
- Auto-reconnect with exponential backoff (1s base, max 30s)
- Typed event handlers
- Cleanup on component unmount

### Unified Chat Store WebSocket
`unifiedChatStore.ts` uses dual slots (sidepanel + fullscreen):
- Lazy-connect per slot: `connectSessionWebSocket()` when streaming starts
- Generation counters per slot to handle async race conditions
- Scoped errors: `caseContextError` vs `sessionError`

## Testing WebSocket Consumers

```python
from channels.testing import WebsocketCommunicator

async def test_chat_consumer():
    communicator = WebsocketCommunicator(AIChatSessionConsumer.as_asgi(), f"/ws/ai-chat/{session.uuid}/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    # Send message
    await communicator.send_json_to({"type": "send_message", "content": "Hello"})
    # Receive events
    response = await communicator.receive_json_from(timeout=10)
    assert response["type"] == "session_state_change"
```
