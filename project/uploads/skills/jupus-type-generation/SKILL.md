---
description: End-to-end TypeScript type generation pipeline from Django models. Use when backend schema changes or frontend types are out of sync.
effort: high
---

# Jupus Type Generation Pipeline

```
Django Models → DRF Spectacular → OpenAPI Schema → @hey-api/openapi-ts → TypeScript Types + Services
```

## Running Type Generation

```bash
./generate_types.sh          # Full generation
./generate_types.sh --check  # Verify types are up-to-date (CI)
```

## What Gets Generated

| File | Contents |
|------|----------|
| `types.gen.ts` | TypeScript interfaces matching serializers |
| `services.gen.ts` | Typed API service classes with methods |
| `schemas.gen.ts` | Schema definitions |
| Core utilities | `CancelablePromise`, `ApiError`, etc. |

## Import Pattern

```typescript
// ALWAYS import from the main index
import { CasesService, type TCase } from '@/types/generated'

// Service usage
const cases = await CasesService.casesList()
const case = await CasesService.casesRetrieve({ uuid: 'abc-123' })
```

## Standard CRUD Methods

| Method | Pattern |
|--------|---------|
| List | `ServiceName.{resource}List()` |
| Retrieve | `ServiceName.{resource}Retrieve({ uuid })` |
| Create | `ServiceName.{resource}Create({ requestBody })` |
| Update | `ServiceName.{resource}PartialUpdate({ uuid, requestBody })` |
| Delete | `ServiceName.{resource}Destroy({ uuid })` |

## When to Regenerate

- After adding/modifying serializers
- After changing `@extend_schema` decorators
- After modifying model fields that affect serializers
- After adding new ViewSets or endpoints

## Troubleshooting

- **Types out of date**: Run `./generate_types.sh`
- **Missing service**: Check that ViewSet is registered in `urls.py` and has `@extend_schema`
- **Parameter errors**: Verify serializer field types match expected TypeScript types
- **Debugging**: Add OpenAPI interceptors to inspect raw schema

## Error Handling

Central error handling catches API errors, logs to Sentry, shows toast notifications.
Only add `try-catch` in components for special business logic (e.g., redirect on 404).
