---
name: jupus-provider-adapter
description: Provider adapter pattern for multi-LLM support. Use when adding new LLM providers, modifying message format translation, or understanding the canonical message format.
effort: high
---

# Provider Adapter Pattern

## Principle (AD-3)

`AIChatSession.messages` stores a **provider-neutral canonical format** (OpenAI-shaped). Provider adapters translate to/from wire format. Transport changes never touch the data model.

## Canonical Message Format (SchemaField)

```python
# Stored in AIChatSession.messages (SchemaField)
class AIChatSessionMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | AssistantMessageChunks
    tool_call_id: Optional[str]
    tool_calls: Optional[list]
    uuid: str
    # ACM additions:
    model_id: Optional[str]       # which model generated this
    token_usage: Optional[dict]   # {"input": N, "output": N}
```

## Adapter Interface

Each provider adapter must:
1. **Convert messages** from canonical -> wire format
2. **Stream responses** yielding `(event_type, data)` tuples matching the contract
3. **Track tokens** across multi-pass tool interactions
4. **Handle tool calls** in the provider's native format

## OpenAI Adapter (Existing)

**File**: `app/ai/ai.py` — `AI` class

- Direct OpenAI SDK usage
- `get_structured_response_stream()` yields `(event_type, data)` tuples
- Tool calls: OpenAI function-calling format natively
- No message conversion needed (canonical IS OpenAI format)

## Bedrock/Anthropic Adapter (New — ACM-026)

**Directory**: `app/ai/services/chat/bedrock/`

6 modules handle the translation:

```
Canonical messages (OpenAI-shaped)
    → message_conversion.py → Converse format
    → client.py → boto3 converse_stream
    → stream_parser.py → Back to (event_type, data) tuples
    → tool_orchestrator.py → Bounded tool loop
    → token_tracker.py → Multi-pass accounting
    → tool_conversion.py → Schema translation
```

### Key Differences

| Aspect | OpenAI | Bedrock Converse |
|--------|--------|-----------------|
| System prompt | In messages array | Separate `system` parameter |
| Tool schema | `{"type": "function", "function": {...}}` | `{"toolSpec": {"name": ..., "inputSchema": {"json": ...}}}` |
| Tool result | `{"role": "tool", "tool_call_id": "...", "content": "..."}` | `{"role": "user", "content": [{"toolResult": {"toolUseId": "...", ...}}]}` |
| Streaming | SSE with delta objects | Binary event stream with typed events |
| Message roles | system, user, assistant, tool | user, assistant (system separate) |
| Stop reasons | finish_reason: stop/tool_calls/length | stopReason: end_turn/tool_use/max_tokens |

## Adding a Third Provider (Future)

1. Create `app/ai/services/chat/<provider>/` directory
2. Implement the same 6-module pattern:
   - `client.py` — API client lifecycle
   - `tool_conversion.py` — Tool schema adapter
   - `message_conversion.py` — Message format adapter
   - `stream_parser.py` — Stream -> `(event_type, data)` tuples
   - `token_tracker.py` — Token accounting
   - `tool_orchestrator.py` — Tool loop management
3. Register in `ModelResolutionService` provider routing
4. Add provider choice to `AIModelConfiguration.provider`
5. Add routing in `send_message_stream.py`

## Message Format Duality

Internally, everything uses OpenAI-shaped chunks. The Bedrock adapter:
- **Inbound**: Converts canonical -> Converse format for the API call
- **Outbound**: Converts Converse events back to OpenAI-shaped `(event_type, data)` for the consumer

This means `AIChatConsumer` and the frontend never know which provider is being used.

## Frontend Impact

None for Phases 0-2. The WebSocket event contract is identical regardless of provider.
Phase 3 (ACM-024) adds model selector UI, but the streaming protocol stays the same.
