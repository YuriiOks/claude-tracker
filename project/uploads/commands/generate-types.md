---
description: Regenerate TypeScript types from Django OpenAPI schema
---

Regenerate frontend TypeScript types from the backend schema.

Steps:
1. Run `./generate_types.sh` from the project root
2. If it fails, check that the Django app is running (`docker compose ps`)
3. Verify generated files updated: check `spa-frontend/src/types/generated/` timestamps
4. Run `./generate_types.sh --check` to confirm types are in sync
5. Report which files were updated
