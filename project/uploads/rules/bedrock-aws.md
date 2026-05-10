---
paths:
  - "app/ai/**"
  - "**/bedrock/**"
---

# AWS Bedrock Converse API Patterns

## Client Lifecycle

```python
from botocore.config import Config

config = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
    read_timeout=120,
    connect_timeout=10,
    max_pool_connections=25,
)
client = boto3.client("bedrock-runtime", region_name=settings.AWS_BEDROCK_REGION, config=config)
```

- **Thread-safe**: boto3 clients can be shared across threads (boto3 Sessions cannot)
- **Lazy initialization**: Create per-process, not at import time
- **Celery**: Reset client on `worker_process_init` signal (clients created before fork() hang)
- **Singleton pattern**: One client per process, not per request

## Tool Schema Conversion (OpenAI -> Anthropic)

OpenAI format:
```python
{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
```

Anthropic `toolSpec` format:
```python
{"toolSpec": {"name": "...", "description": "...", "inputSchema": {"json": {...}}}}
```

**Strip these fields** from parameters before conversion:
- `strict` (OpenAI-only)
- `additionalProperties` (OpenAI-only)

**Keep the `"json"` wrapper** inside `inputSchema` — omitting it causes `ValidationException`.

## Streaming Event Types (converse_stream)

```
messageStart         -> {"role": "assistant"}
contentBlockStart    -> {"contentBlockIndex": N, "start": {"text": ""} | {"toolUse": {"toolUseId": "...", "name": "..."}}}
contentBlockDelta    -> {"contentBlockIndex": N, "delta": {"text": "chunk"} | {"toolUse": {"input": "partial json"}}}
contentBlockStop     -> {"contentBlockIndex": N}
messageStop          -> {"stopReason": "end_turn"|"tool_use"|"max_tokens"|"stop_sequence"}
metadata             -> {"usage": {"inputTokens": N, "outputTokens": N}, "metrics": {"latencyMs": N}}
```

**Tool use input**: `contentBlockDelta` sends incremental JSON string chunks. Concatenate all chunks for a content block, then `json.loads()` after `contentBlockStop`.

## Message Ordering Rules (CRITICAL)

1. Messages MUST alternate user/assistant — consecutive same-role = `ValidationException`
2. First message MUST be user role
3. System prompt goes in `system` parameter, NOT in messages
4. After `tool_use` stop reason, next message MUST be user with `toolResult` for EVERY `toolUse` block
5. `toolResult` blocks should be FIRST in user content array
6. `toolResult.toolUseId` must reference the immediately preceding assistant message
7. Empty content `[]` or empty text `""` = `ValidationException`

## Tool Calling Protocol

```python
# Step 1: Model returns stopReason="tool_use" with toolUse blocks
# Step 2: Execute tool, build user message with toolResult
messages.append(assistant_message)  # full assistant message with toolUse
messages.append({
    "role": "user",
    "content": [
        {"toolResult": {"toolUseId": "exact_id_from_toolUse", "content": [{"text": "result"}], "status": "success"}}
    ]
})
# Step 3: Call converse_stream again with updated messages
```

## Retryable Errors

| Error | Retry? | Strategy |
|-------|--------|----------|
| `ThrottlingException` | Yes | Exponential backoff |
| `ServiceUnavailableException` | Yes | Backoff + retry |
| `ModelTimeoutException` | Yes | Retry with shorter input |
| `ModelStreamErrorException` | Yes | Retry entire call |
| `ValidationException` | No | Fix the request |
| `AccessDeniedException` | No | Fix IAM / model access |

All Bedrock Converse calls MUST be wrapped in `traced_bedrock_generation` from `ai/services/chat/bedrock/tracing.py` — it emits a Langfuse generation span, classifies failures into `BedrockErrorCategory` (filterable as `metadata.error_category`), captures partial text/tool-call state on error, and flushes token deltas so billing data survives the error path.

## Token Tracking

- Input tokens grow with each turn (full history re-sent every call)
- Tool definitions consume tokens on every call
- Track across multi-pass tool loops: accumulate `inputTokens` + `outputTokens` from each call's metadata event
- Stream: token counts in final `metadata` event only

## Connection Management

- Always fully consume the event stream — breaking early leaks HTTP connections
- Use `eu.anthropic.claude-*` model IDs for EU region (Bedrock model IDs have region prefix)
