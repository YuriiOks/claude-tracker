---
paths:
  - "app/ai/**"
  - "spa-frontend/src/components/app/chat/**"
  - "spa-frontend/src/store/app/globalChat/**"
  - "spa-frontend/src/store/app/unifiedChat/**"
---

# ACM (AI Chat Merger) Architecture — Locked Decisions

Reference: `docs/ACM_project/MASTER-PLAN.md`, `docs/ACM_project/TDD.md`

## Architectural Decisions (ALL LOCKED — do not deviate)

1. **boto3 `converse_stream` + IAM/SigV4** — not httpx+bearer. Auto-rotating credentials, adaptive retry, model-agnostic Converse format.

2. **DB-backed model catalog** — `AIModelConfiguration` table is admin-editable without deploys. Supports per-org policies, capability flags, cost tiers.

3. **Provider adapter pattern** — `AIChatSession.messages` stays provider-neutral (OpenAI-shaped). Adapters translate to/from wire format. Transport changes don't touch data model.

4. **Bounded tool loop** — Max N iterations (default 3, configurable via `BEDROCK_MAX_TOOL_ITERATIONS`). Not hardcoded 2-pass.

5. **Block, don't silent-fallback** — If user explicitly chose Claude and it's unavailable: return `MODEL_UNAVAILABLE` error. Auto mode can silently fallback.

6. **Per-message `effective_model` metadata** — Every assistant message records which model generated it.

7. **django-waffle for feature flags** — `claude_models_enabled` flag gates all Claude models. Check `flag.everyone` directly in WS consumers (no HttpRequest available). NOTE: This is NEW — existing features use PostHog (`app/jupus/feature_flags.py`). Both coexist.

8. **Org-level model policy from day 1** — `OrgModelPolicy` table exists even if V1 treats all orgs identically.

## Phase Plan

| Phase | Ticket | Points | Scope |
|-------|--------|--------|-------|
| 0 (Foundation) | — | — | AIModelConfiguration + OrgModelPolicy models, waffle flag, `model` field on session, ModelResolutionService |
| 1 | ACM-026 | 5 | Bedrock tool calling: 6 new modules in `app/ai/services/chat/bedrock/` |
| 2 | ACM-025 | 3 | Per-session model selection, available_models endpoint, WS model events |
| 3 | ACM-024 | 2 | Frontend ModelSelector.vue, useModelSelection.ts composable |
| 4 | ACM-023 | 2 | Team history, IsSessionOwnerOrReadOnly permission, `mine` filter |

## Key File Paths

| New File | Purpose |
|----------|---------|
| `app/ai/models/model_configuration.py` | AIModelConfiguration + OrgModelPolicy models |
| `app/ai/services/chat/session/model_resolution.py` | ModelResolutionService |
| `app/ai/services/chat/bedrock/client.py` | boto3 singleton client |
| `app/ai/services/chat/bedrock/tool_conversion.py` | OpenAI -> Anthropic schema |
| `app/ai/services/chat/bedrock/message_conversion.py` | Message format adapter |
| `app/ai/services/chat/bedrock/stream_parser.py` | Converse events -> OpenAI chunks |
| `app/ai/services/chat/bedrock/token_tracker.py` | Multi-pass token accounting |
| `app/ai/services/chat/bedrock/tool_orchestrator.py` | Bounded tool loop |
| `spa-frontend/src/components/app/chat/components/ModelSelector.vue` | Model dropdown |
| `spa-frontend/src/composables/useModelSelection.ts` | Model WS events composable |

## Existing Files Modified

| File | Change |
|------|--------|
| `app/ai/ai.py` | Already has POC branch with `_is_bedrock_model()` and `_convert_messages_for_anthropic()` |
| `app/ai/consumers.py` | Add model field handling, ownership check, model WS events |
| `app/ai/services/chat/session/ai_chat_session_send_message_stream.py` | Route to Bedrock adapter based on provider |
| `app/ai/models/chat/session.py` | Add `model` CharField |
| `spa-frontend/src/store/app/globalChat/globalChatStore.ts` | Add availableModels state |

## Feature Flag Strategy

```python
# In WebSocket consumer (no HttpRequest):
from waffle import get_waffle_flag_model
Flag = get_waffle_flag_model()
flag = Flag.objects.get(name='claude_models_enabled')
# Check flag.everyone directly, or flag.is_active_for_user(scope["user"]) on waffle v5.0.0+

# In tests:
from waffle.testutils import override_flag
@override_flag('claude_models_enabled', active=True)
def test_claude_model_available(self):
    ...
```

## WS Event Types (New for ACM)

- `model_resolved` — confirms which model will handle the request
- `model_fallback` — model was unavailable, fell back to default (auto mode only)
- `model_error` — explicit model selection failed, no fallback
