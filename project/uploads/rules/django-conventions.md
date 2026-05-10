---
paths:
  - "app/**/*.py"
---

# Django Conventions

## ORM
- Use `.create()` over `obj = Model(); obj.save()` to avoid race conditions
- Use `select_related()` for FK joins, `prefetch_related()` for M2M/reverse FK
- Use `F()` expressions for atomic updates: `Model.objects.filter(pk=pk).update(count=F('count') + 1)`
- Prefer `.filter().update()` for bulk operations over iterating `.save()`

## Error Handling
- No bare `except:` blocks — always catch specific exceptions
- In DRF views, let the framework handle response codes based on exception type
- Only use try/catch when you need custom error handling beyond DRF defaults
- Use `raise ValidationError(...)` for input validation errors

## Migrations
- After pulling: `docker-compose exec app python manage.py showmigrations | grep '\[ \]'`
- Run pending: `docker-compose exec app python manage.py migrate`
- Create new: `docker-compose exec app python manage.py makemigrations <app_name>`
- Never edit migrations that have already been applied in production

## Testing
- Run tests: `docker compose run app py.test`
- Specific app: `docker compose run app py.test app/<app_name>/ -v`
- Use `factory_boy` factories for test data, not manual `.create()` in tests
- Prefer `pytest` fixtures over `setUp`/`tearDown`

## Org-Scoped Queries (CRITICAL SECURITY)

Every queryset and object lookup MUST be scoped to the user's org. This is the #1 pentest finding — IDOR via unscoped UUID lookups.

```python
# GOOD — uses get_queryset() which already filters by org
obj = self.get_object()

# GOOD — explicit org scope on manual lookup
org = get_object_or_404(Organisation, uuid=uuid, id=self.request.user.org.id)
case = get_object_or_404(Case, uuid=uuid, org=self.request.user.org)

# BAD — any user can access any org's data by guessing UUID
org = get_object_or_404(Organisation, uuid=uuid)  # NEVER DO THIS
case = Case.objects.get(uuid=uuid)                 # NEVER DO THIS
```

Rules:
1. **In ViewSets**: Always use `self.get_object()` — it respects `get_queryset()` which filters by org/role
2. **In `@action` methods**: If you must do a manual lookup, ALWAYS include `org=self.request.user.org`
3. **In service functions**: Accept and filter by org, never trust UUID alone
4. **No exceptions**: Even for SUPERUSER-only endpoints, use `get_queryset()` — roles change, code gets copied

## API (DRF)
- ViewSets with role-based permissions per action
- Serializers validate input, not views
- Use `@action` decorator for custom endpoints
- API versioning via URL prefix
