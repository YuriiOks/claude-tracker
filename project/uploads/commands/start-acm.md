# ACM Session Startup

Load context for working on the AI Chat Merger project.

## Steps

1. Read the current phase status:
   - `docs/ACM_project/MASTER-PLAN.md` (implementation plan)
   - Check git branches for ACM work: `git branch | grep -i acm`

2. Check Yurii's 4 tickets:
   - **ACM-026** (Phase 1, 5pts): Bedrock Tool Calling — `app/ai/services/chat/bedrock/`
   - **ACM-025** (Phase 2, 3pts): Per-Session Model Selection — `app/ai/services/chat/session/model_resolution.py`
   - **ACM-024** (Phase 3, 2pts): Frontend Model Selector — `spa-frontend/src/components/app/chat/components/ModelSelector.vue`
   - **ACM-023** (Phase 4, 2pts): Team History + Permissions

3. Check recent changes:
   - `git log --oneline -10 -- app/ai/`
   - `git log --oneline -10 -- spa-frontend/src/components/app/chat/`

4. Check migration status:
   - `docker compose run app python manage.py showmigrations ai | grep '\[ \]'`

5. Report:
   - Current branch + uncommitted changes
   - Which ACM phase is active
   - What files were recently modified
   - Any pending migrations
   - Suggested next action based on ticket status

## Key Documentation
- Architecture: `docs/ACM_project/MASTER-PLAN.md`
- TDD spec: `docs/ACM_project/TDD.md`
- Research: `docs/ACM_project/ACM-RESEARCH-SYNTHESIS.md`
- Codebase audit: `docs/ACM_project/FACTBASE_ACM.md`

## Key Source Files
- LLM integration: `app/ai/ai.py`
- Chat session model: `app/ai/models/chat/session.py`
- WebSocket consumer: `app/ai/consumers.py`
- Streaming service: `app/ai/services/chat/session/ai_chat_session_send_message_stream.py`
- Tool definition: `app/ai/services/chat/tools/search_court_database.py`
- Feature flags: `app/jupus/feature_flags.py` (PostHog) + django-waffle (ACM-new)
