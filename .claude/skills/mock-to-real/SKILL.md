---
name: mock-to-real
description: Migrate one key in src/data.js (REPOS, GLOBAL, SESSIONS, LIVE_EVENTS_*) from mocked-only to backend-served, with mock fallback retained. The per-key workflow for executing MASTER_PLAN.md.
disable-model-invocation: true
origin: claude-tracker
---

# mock-to-real -- per-key migration

Each `src/data.js` export gets migrated independently. The endpoint mirrors the shape; the frontend swaps from `import { FOO } from './data'` to `const foo = useFoo()`, and `useFetch` keeps the mock as the fallback so the UI never flashes empty.

## When to use

- The mock has stabilized (no shape changes in the last few sessions).
- The backend has (or can have) a service producing the same data from a real source.
- The data is **read-only** for the dashboard. Writes are out of scope for this skill.

## The shape of the migration

```
BEFORE:                                  AFTER:
component                                component
  | imports                                | calls
  v                                        v
data.js (MOCK)                           api.js hook
                                           | fetches
                                           v
                                         backend /api/<resource>
                                           | falls back to
                                           v
                                         data.js (still imported as fallback)
```

`data.js` is NOT removed. It remains the design-time fallback and seeds `useFetch`'s initial state.

## Workflow

### Pre-flight

```bash
grep -rn "<KEY>" src/                     # every consumer
grep -rn "<KEY>" backend/app/             # is there already a service?
grep -A5 "<key>" MASTER_PLAN.md           # any pre-existing migration notes
```

If `MASTER_PLAN.md` has a row for this key, follow its notes first.

### 1. Backend service -- produce the data

Add or extend `backend/app/services/<resource>.py`:

```python
async def load_resources() -> list[Resource]:
    """Read from ~/.claude/projects/ JSONL OR per-repo .claude/ folders OR
    SQLite cache -- whatever the real source is. Returns objects matching
    the Pydantic schema (which mirrors data.js)."""
    settings = get_settings()
    ...
    return items
```

For JSONL parsing, **delegate to `jsonl-parser-specialist`**.

### 2. Pydantic schema -- mirror data.js exactly

`backend/app/schemas/<resource>.py` -- see `skill: api-endpoint-add` step 2.

Verify field-by-field against `src/data.js`. Common drift:
- `tokensWeek` vs `tokens_week` -> use `alias_generator=to_camel`.
- Numeric separators (`4_820_000`) -> ints on the wire; just integer JSON.
- `permissions: { allow, deny, ask }` -> object, not array of rules.

### 3. Router -- expose the endpoint

`backend/app/routers/<resource>.py` -- see `skill: api-endpoint-add` step 3.

### 4. Frontend hook -- wire with fallback

`src/api.js`:

```js
export function useResources() {
  // MOCK.RESOURCES is the existing data.js export -- pass it as fallback
  // so the UI hydrates instantly and survives backend downtime.
  return useFetch('/api/<resource>s', MOCK.RESOURCES);
}
```

### 5. Swap component imports

Find every consumer and change:

```js
// BEFORE
import { RESOURCES } from './data';
function Foo() {
  return <List items={RESOURCES} />;
}

// AFTER
import { useResources } from './api';
function Foo() {
  const items = useResources();
  return <List items={items} />;
}
```

`useFetch` returns the mock when `VITE_USE_MOCKS=1` OR the backend errors, so `items` is never `null` -- components don't need null guards.

### 6. Verify in BOTH modes

```bash
make dev                                  # backend up -- real data flows
VITE_USE_MOCKS=1 npm run dev              # mock-only -- should look IDENTICAL
make docker-down && npm run dev           # backend down -- falls back to mock
```

In each mode: visit the affected screen in BOTH themes (`rules/dual-theme.md`).

### 7. Test

```bash
make test                                 # backend pytest
npm run lint
```

### 8. Document

Append a line to `MASTER_PLAN.md` marking the key as migrated, with the date.

## Anti-patterns

- Deleting `data.js` exports after migration. They stay as the fallback.
- Letting the backend shape drift from `data.js`. The mirror is the contract -- both directions.
- Migrating a key while shape is still in flux. Stabilize first.
- Adding `if (data) { ... }` null guards in components. `useFetch` returns the fallback, never null.
- Mocking inside the component (`const items = useResources() ?? STATIC_FALLBACK`). The fallback is centralized.

## Cross-references

- `agent: backend-engineer` -- backend implementation
- `agent: data-shape-keeper` -- shape questions
- `agent: jsonl-parser-specialist` -- when the source is JSONL transcripts
- `skill: api-endpoint-add` -- multi-file endpoint scaffolder
- `MASTER_PLAN.md` -- full migration plan per key
- `src/api.js` -- the `useFetch` helper
