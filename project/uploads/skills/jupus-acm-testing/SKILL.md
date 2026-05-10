---
name: jupus-acm-testing
description: TDD patterns for the ACM project. 78 planned tests across 10 files. Mock patterns for boto3 Bedrock (moto unsupported), waffle flag testing, fixture builders. Use when writing or modifying ACM tests.
effort: high
---

# ACM Test-Driven Development Guide

Reference: `docs/ACM_project/TDD.md`

## Framework

- **pytest** + **pytest-django** + **pytest-asyncio**
- **Mocking**: `unittest.mock` (moto does NOT support bedrock-runtime)
- **Waffle testing**: `waffle.testutils.override_flag` / `override_switch`
- **Factories**: Use existing `ai_chat_session_create()` service

## Test Files (78 Total)

| File | Ticket | Tests | Focus |
|------|--------|-------|-------|
| `test_bedrock_tool_conversion.py` | ACM-026 | 7 | OpenAI -> Anthropic schema |
| `test_bedrock_message_conversion.py` | ACM-026 | 10 | Message format adapter |
| `test_bedrock_stream_parser.py` | ACM-026 | 8 | Converse event parsing |
| `test_bedrock_token_tracker.py` | ACM-026 | 4 | Multi-pass accumulation |
| `test_bedrock_tool_orchestrator.py` | ACM-026 | 6 | Bounded tool loop |
| `test_bedrock_client.py` | ACM-026 | 3 | Client lifecycle |
| `test_model_configuration.py` | ACM-025 | 8 | Model table + org policy |
| `test_model_resolution.py` | ACM-025 | 12 | Resolution service logic |
| `test_per_session_model.py` | ACM-025 | 9 | Session model field + API |
| `test_chat_history_team_filter.py` | ACM-023 | 11 | Permissions + filtering |

## Mock Patterns

### Bedrock Stream Mock

```python
def make_converse_stream_response(text="Hello", tool_call=None):
    """Build a mock converse_stream response with event iterator."""
    events = [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {"text": ""}}},
    ]
    for chunk in [text[i:i+5] for i in range(0, len(text), 5)]:
        events.append({"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": chunk}}})
    events.append({"contentBlockStop": {"contentBlockIndex": 0}})
    
    if tool_call:
        idx = 1
        events.append({"contentBlockStart": {"contentBlockIndex": idx, "start": {"toolUse": {"toolUseId": "tool_1", "name": tool_call["name"]}}}})
        events.append({"contentBlockDelta": {"contentBlockIndex": idx, "delta": {"toolUse": {"input": json.dumps(tool_call["input"])}}}})
        events.append({"contentBlockStop": {"contentBlockIndex": idx}})
        events.append({"messageStop": {"stopReason": "tool_use"}})
    else:
        events.append({"messageStop": {"stopReason": "end_turn"}})
    
    events.append({"metadata": {"usage": {"inputTokens": 100, "outputTokens": 50}, "metrics": {"latencyMs": 500}}})
    return {"stream": iter(events)}
```

### Tool Fixture

```python
@pytest.fixture
def openai_court_tool():
    """SEARCH_COURT_DATABASE in OpenAI function-calling format."""
    from app.ai.services.chat.tools.search_court_database import SEARCH_COURT_DATABASE_TOOL
    return SEARCH_COURT_DATABASE_TOOL
```

### Waffle Flag Testing

```python
from waffle.testutils import override_flag

@override_flag('claude_models_enabled', active=True)
def test_claude_models_visible_when_flag_on(self, api_client, user):
    response = api_client.get('/api/ai-chat/sessions/available_models/')
    model_ids = [m['model_id'] for m in response.data]
    assert any('claude' in m for m in model_ids)

@override_flag('claude_models_enabled', active=False)
def test_claude_models_hidden_when_flag_off(self, api_client, user):
    response = api_client.get('/api/ai-chat/sessions/available_models/')
    model_ids = [m['model_id'] for m in response.data]
    assert not any('claude' in m for m in model_ids)
```

### Model Configuration Factory

```python
@pytest.fixture
def seed_model_configs(db):
    """Seed AIModelConfiguration with 4 models (2 OpenAI, 2 Claude)."""
    from app.ai.models.model_configuration import AIModelConfiguration
    configs = [
        AIModelConfiguration(model_id="gpt-5.4", display_label="GPT-5.4", provider="openai", is_enabled=True, is_default=True, supports_tools=True),
        AIModelConfiguration(model_id="gpt-5.4-mini", display_label="GPT-5.4 Mini", provider="openai", is_enabled=True, supports_tools=True),
        AIModelConfiguration(model_id="eu.anthropic.claude-sonnet-4-6", display_label="Claude Sonnet 4.6", provider="anthropic", is_enabled=True, supports_tools=True, feature_flag="claude_models_enabled"),
        AIModelConfiguration(model_id="eu.anthropic.claude-opus-4-6-v1", display_label="Claude Opus 4.6", provider="anthropic", is_enabled=True, supports_tools=True, supports_thinking=True, feature_flag="claude_models_enabled"),
    ]
    AIModelConfiguration.objects.bulk_create(configs)
    return configs
```

## TDD Workflow

1. Write the test file FIRST (red)
2. Implement the module (green)
3. Refactor while tests stay green
4. Run: `docker compose run app py.test app/tests/test_ai/test_services/test_bedrock_*.py -v`

## Test Location

All ACM tests go in: `app/tests/test_ai/test_services/`

Follow existing patterns from `test_chat_session_send_message_stream.py`.

## Running Tests

```bash
# All Bedrock tests
docker compose run app py.test app/tests/test_ai/test_services/test_bedrock_*.py -v

# All ACM tests
docker compose run app py.test app/tests/test_ai/test_services/ -k "bedrock or model_configuration or model_resolution or per_session_model or chat_history_team" -v

# Single file
docker compose run app py.test app/tests/test_ai/test_services/test_bedrock_tool_conversion.py -v
```
