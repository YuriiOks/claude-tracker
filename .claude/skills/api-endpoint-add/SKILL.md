---
name: api-endpoint-add
description: Scaffold a new FastAPI endpoint + matching src/api.js hook + Pydantic schema, keeping the backend wire format aligned with src/data.js. Use when surfacing a new resource from backend to dashboard.
disable-model-invocation: true
origin: claude-tracker
---

# api-endpoint-add -- multi-file endpoint scaffolder

Adding a new backend endpoint that a dashboard screen will consume touches **4 files minimum**:

| Layer | File | Role |
|---|---|---|
| Schema | `backend/app/schemas/<resource>.py` | Pydantic model with camelCase aliases (wire format = data.js shape) |
| Router | `backend/app/routers/<resource>.py` | FastAPI router; mounted under `/api` |
| Mount | `backend/app/main.py` | `app.include_router(...)` line |
| Hook | `src/api.js` | `useFoo()` with mock fallback to `MOCK.FOO` |

Plus optionally:
- `backend/app/services/<resource>.py` if there's parsing/IO logic
- `backend/tests/test_<resource>.py` for the router
- Component update to call the hook (or that's a separate task for `react-engineer`)

## Workflow

### 1. Confirm the data shape

The Pydantic schema MUST mirror an existing `src/data.js` key (or one you're adding). If you're inventing a new shape, **stop** -- coordinate with `data-shape-keeper` first.

```bash
grep -n "<resource>" src/data.js src/api.js
```

### 2. Pydantic schema

`backend/app/schemas/<resource>.py`:

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Resource(BaseModel):
    """Mirrors `<RESOURCE>` in src/data.js. Wire format: camelCase."""
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    id: str
    # ... fields matching data.js exactly: snake_case in code, camelCase on the wire
```

Export from `backend/app/schemas/__init__.py` if there's an aggregator.

### 3. Router

`backend/app/routers/<resource>.py`:

```python
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.schemas.<resource> import Resource

router = APIRouter(tags=["<resource>"])


@router.get("/<resource>s", response_model=list[Resource])
async def list_resources() -> list[Resource]:
    return []


@router.get("/<resource>s/{resource_id}", response_model=Resource)
async def get_resource(resource_id: str) -> Resource:
    raise HTTPException(501, "not implemented")
```

### 4. Mount in main.py

`backend/app/main.py` -- add to imports and `include_router` block:

```python
from app.routers import <resource>
# ...
app.include_router(<resource>.router, prefix="/api")
```

### 5. Frontend hook

`src/api.js` -- add a hook that uses `useFetch(path, fallback)`:

```js
export function useResources() {
  return useFetch('/api/<resource>s', MOCK.RESOURCES);
}

export function useResource(id) {
  return useFetch(
    id ? `/api/<resource>s/${id}` : null,
    MOCK.RESOURCES?.find(r => r.id === id),
  );
}
```

The `useFetch` helper already handles: `VITE_USE_MOCKS=1` returns mock; backend 5xx falls back to mock; sessionStorage cache prevents reload flash.

### 6. Test

`backend/tests/test_<resource>.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app


@pytest.mark.asyncio
async def test_list_resources():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/api/<resource>s")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

### 7. Verify

```bash
make test                                                # backend pytest
make dev                                                 # both servers
curl -s http://127.0.0.1:8765/api/<resource>s | jq .
npm run lint                                             # frontend eslint
```

Eyeball the dashboard screen that consumes the new hook in BOTH themes (per `rules/dual-theme.md`).

## Anti-patterns

- Forgetting `alias_generator=to_camel` -- wire format ends up `snake_case` and components break silently.
- Adding a field on the backend that isn't in `src/data.js` -- breaks the mirror contract.
- Sync `def` handler. FastAPI accepts it but it blocks the loop.
- Catching all exceptions in the router. Let FastAPI return 500; log in the service.
- Hardcoding paths in the router. Settings live in `app.config.get_settings()`.

## Cross-references

- `agent: backend-engineer` -- broader backend questions
- `agent: data-shape-keeper` -- new shape OR rename
- `skill: data-shape` -- the four data.js shapes
- `skill: mock-to-real` -- migrating an existing mocked key
- `backend/README.md` -- current endpoint catalog
