---
paths:
  - "**/migrations/**"
  - "**/models/**"
---

# Migration Guidelines (Enforced)

Source: `docs/docs/code/development-practices/migrations.md` (commit d666571)

## Linear Chain Rule

Jupus enforces a **linear migration chain** (003 -> 002 -> 001). No merge migrations except legacy ones already in the codebase.

## Hard Rules

1. **Never add merge migrations** — resolve conflicts by rebasing
2. **PR must be up-to-date with master** before merging if it includes migrations
3. **Never modify migrations already on master** — they may be applied on staging/production
4. **Never modify table schema with raw SQL**
5. **Never modify Django's internal migration table**
6. **Never modify the migration compliance check script**
7. **Always use `python manage.py makemigrations`** — never write migrations manually

## AI Agent Guardrail

> "AI agents get this wrong consistently, even if explicitly instructed to do so."
> — Migration guidelines, on rollback-before-delete ordering

## Conflict Resolution (Exact Order Matters)

When your migration conflicts with one merged to master:

1. **FIRST**: Roll back to your starting point: `docker compose run app python manage.py migrate <app> <number>`
   - Do this BEFORE changing any code or deleting migrations
   - If you delete the migration file first, Django cannot execute the reverse operation
2. **THEN**: Delete your migration file (it's not on master, so this is safe)
3. **THEN**: Rebase/merge to latest master
4. **THEN**: Re-generate: `docker compose run app python manage.py makemigrations`
5. **THEN**: Apply and test: `docker compose run app python manage.py migrate`

## Destructive Migration Review

Migrations can execute arbitrary Python, manipulate data, drop columns/tables. Always:
- Review migration content before committing
- Test rollback: `python manage.py migrate <app> <previous_number>`
- If a harmful migration reaches master: halt deployments immediately, contact lead engineer

## Commands (Always in Docker)

```bash
docker compose run app python manage.py showmigrations          # Check status
docker compose run app python manage.py showmigrations | grep '\[ \]'  # Pending only
docker compose run app python manage.py migrate                  # Apply all
docker compose run app python manage.py migrate <app> <number>   # Rollback to specific
docker compose run app python manage.py makemigrations <app>     # Generate
```
