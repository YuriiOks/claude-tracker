---
name: jupus-bedrock-adapter
description: Build and modify the 6 Bedrock adapter modules for AWS Converse API integration. Use when working on ACM-026 (Bedrock Tool Calling) or any Bedrock-related code in app/ai/services/chat/bedrock/.
effort: high
---

# Bedrock Adapter Development Guide

## Module Overview (6 files in `app/ai/services/chat/bedrock/`)

### 1. `client.py` — boto3 Client Singleton

```python
import boto3
from botocore.config import Config
from django.conf import settings

_client = None

def get_bedrock_client():
    global _client
    if _client is None:
        config = Config(
            retries={"max_attempts": 5, "mode": "adaptive"},
            read_timeout=120,
            connect_timeout=10,
            max_pool_connections=25,
        )
        _client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_BEDROCK_REGION,
            config=config,
        )
    return _client

def reset_client():
    """Call from Celery worker_process_init signal."""
    global _client
    _client = None
```

**Rules:**
- Lazy initialization — never at module import time
- Thread-safe: boto3 clients are safe to share across threads
- Call `reset_client()` from `worker_process_init` (pre-fork clients hang in Celery workers)

### 2. `tool_conversion.py` — OpenAI -> Anthropic Schema

Convert the existing `SEARCH_COURT_DATABASE_TOOL` (OpenAI format) to Anthropic `toolSpec`:

```python
def convert_openai_tool_to_anthropic(tool: dict) -> dict:
    """Convert OpenAI function schema to Anthropic toolSpec."""
    func = tool["function"]
    params = {k: v for k, v in func["parameters"].items()
              if k not in ("strict", "additionalProperties")}
    return {
        "toolSpec": {
            "name": func["name"],
            "description": func["description"],
            "inputSchema": {"json": params},
        }
    }
```

**Gotchas:**
- Strip `strict` and `additionalProperties` — Anthropic doesn't support them
- Keep the `"json"` wrapper inside `inputSchema`
- `name` must match `^[a-zA-Z0-9_-]+$`

### 3. `message_conversion.py` — OpenAI <-> Converse Format

```python
def convert_messages_to_converse(messages: list[dict], system_prompt: str) -> tuple[list, list]:
    """Returns (system_list, message_list) for Converse API.
    
    System prompt is hoisted out of messages into separate param.
    Tool results must be FIRST in user content blocks.
    Strict alternating user/assistant turns enforced.
    """
```

**Critical rules:**
- System prompt: extract to `system=[{"text": "..."}]` parameter (NOT in messages)
- `toolResult` blocks FIRST in user message content array
- Tool_use blocks preserve `toolUseId` and `input`
- Enforce strict alternating turns (merge consecutive same-role if needed)
- Map `tool` role messages -> `user` role with `toolResult` content

### 4. `stream_parser.py` — Converse Events -> OpenAI Chunks

Parse `converse_stream` event types and yield OpenAI-shaped chunks that `_first_pass()` in `send_message_stream.py` expects:

```python
def parse_converse_stream(response) -> Generator[tuple[str, dict], None, dict]:
    """Yield (event_type, data) tuples matching existing streaming contract.
    
    Returns metadata dict (usage, metrics) after stream exhaustion.
    """
    tool_inputs = {}  # contentBlockIndex -> accumulated JSON string
    
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"]
            idx = delta["contentBlockIndex"]
            if "text" in delta.get("delta", {}):
                yield ("text_delta", {"delta": delta["delta"]["text"]})
            elif "toolUse" in delta.get("delta", {}):
                tool_inputs.setdefault(idx, "")
                tool_inputs[idx] += delta["delta"]["toolUse"]["input"]
        elif "messageStop" in event:
            if event["messageStop"]["stopReason"] == "tool_use":
                # Parse accumulated tool JSON and yield tool_call
                for idx, json_str in tool_inputs.items():
                    yield ("tool_call", {"input": json.loads(json_str), ...})
        elif "metadata" in event:
            return event["metadata"]
```

**Must preserve**: The existing streaming contract — `send_message_stream.py`'s `_first_pass()` expects `(event_type, data)` tuples with types: `text_delta`, `text_chunk_end`, `chunk`, `tool_call`.

### 5. `token_tracker.py` — Multi-Pass Accounting

```python
class TokenTracker:
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.passes = 0
    
    def record_pass(self, usage: dict):
        self.total_input += usage["inputTokens"]
        self.total_output += usage["outputTokens"]
        self.passes += 1
    
    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output
```

Accumulates across 1-3 tool loop iterations. Used for per-message metadata and billing.

### 6. `tool_orchestrator.py` — Bounded Tool Loop

```python
async def orchestrate_tool_calls(
    client, messages, tools, system,
    max_iterations=settings.BEDROCK_MAX_TOOL_ITERATIONS,  # default 3
) -> Generator[tuple[str, dict], None, None]:
    """Execute bounded tool loop:
    1. Call converse_stream
    2. If tool_use: execute tool, append result, re-call (up to max_iterations)
    3. If end_turn: yield final response
    """
```

**Default**: `BEDROCK_MAX_TOOL_ITERATIONS = 3` (configurable in settings)

## Integration Points

### `send_message_stream.py` Changes
- Check `_is_bedrock_model(session.model)` to route to Bedrock adapter
- Replace direct OpenAI call with Bedrock adapter call
- Token tracking: use `TokenTracker` instead of single-pass counting
- Tool handling: delegate to `tool_orchestrator` instead of inline 2-pass

### `consumers.py` Changes (ACM-025)
- Accept `model` field in `send_message` WS message
- Emit `model_resolved` / `model_fallback` / `model_error` events
- Pass model to `send_message_stream()`

## Testing (See jupus-acm-testing skill)

- moto does NOT support `bedrock-runtime` — use `unittest.mock`
- Mock `client.converse_stream()` return value with fake event stream
- Test tool_conversion with real `SEARCH_COURT_DATABASE_TOOL` schema
