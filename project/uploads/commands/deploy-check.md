---
description: Pre-deployment checklist before merging to staging or production
---

Run pre-deployment verification for the current branch.

Steps:
1. Check day of week — WARN if Friday or day before a holiday
2. Run tests: `pytest app/tests/ -v`
3. Run lint: `ruff check app/`
4. Check migrations: `python manage.py makemigrations --check`
5. Check for hardcoded secrets: search for API keys, passwords, tokens in staged changes
6. Check types in sync: `./generate_types.sh --check`
7. Verify type hints on new/modified functions
8. Report checklist results:
   - [ ] Not Friday/pre-holiday
   - [ ] Tests pass
   - [ ] Lint clean
   - [ ] Migrations up to date
   - [ ] No hardcoded secrets
   - [ ] Types in sync
   - [ ] Type hints present
