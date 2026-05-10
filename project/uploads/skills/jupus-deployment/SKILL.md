---
description: Deployment process and safety checks for the Jupus platform. Use before deploying or when troubleshooting deployment issues.
effort: high
---

# Jupus Deployment

## Branch Strategy

- `staging` branch → staging environment
- `production` branch → production environment
- Merging to either triggers automated deployment

## Automated Deployment Steps

1. **Tests**: Full suite must pass (unit, integration, e2e)
2. **Build**: Fresh Docker build with optimized layers, static assets, TypeScript bundled
3. **Pre-deploy backup**: Timestamped database backup → Azure Blob Storage
4. **Zero-downtime deploy**:
   - Deploy to failover container
   - Switch traffic to failover
   - Update original container
   - Full redundancy maintained throughout
5. **Post-deploy**:
   - Create post-deployment backup
   - GitHub release with semantic versioning
   - Linear release created
   - Related Linear tickets closed

## Pre-Deployment Checklist

- [ ] All tests pass: `pytest app/tests/ -v`
- [ ] Lint clean: `ruff check app/`
- [ ] Migrations created if needed: `python manage.py makemigrations --check`
- [ ] No hardcoded secrets
- [ ] Type hints on new functions
- [ ] Types regenerated if schema changed: `./generate_types.sh --check`
- [ ] NOT a Friday or day before holiday
- [ ] Loom video recorded for PR

## Post-Deployment Verification

- Monitor logs in real-time
- Verify application health endpoints
- Check Linear release status
- Spot-check critical user flows

## Rollback

If issues found post-deploy:
1. Revert merge on the deployment branch
2. Push triggers re-deployment to previous version
3. Restore pre-deploy database backup if data was affected

## Infrastructure

- **Cloud**: Microsoft Azure (separate envs for prod/staging)
- **Containers**: app + app_failover + redis + PostgreSQL + Celery + Celerybeat
- **Secrets**: HashiCorp Vault (auto-injected into containers)
