# ACM Project Status Check

Quick status of the AI Chat Merger project.

## Steps

1. Check git state:
   ```bash
   git branch --show-current
   git log --oneline -5
   git status --short
   ```

2. Check for ACM branches:
   ```bash
   git branch -a | grep -i acm
   ```

3. Check migration status:
   ```bash
   docker compose run app python manage.py showmigrations ai | tail -10
   ```

4. Check if Bedrock modules exist:
   ```bash
   ls -la app/ai/services/chat/bedrock/ 2>/dev/null || echo "Bedrock adapter not yet created"
   ```

5. Check if model configuration exists:
   ```bash
   ls -la app/ai/models/model_configuration.py 2>/dev/null || echo "Model configuration not yet created"
   ```

6. Run ACM tests (if they exist):
   ```bash
   docker compose run app py.test app/tests/test_ai/test_services/ -k "bedrock or model_configuration or model_resolution" -v --no-header 2>/dev/null || echo "No ACM tests yet"
   ```

7. Report summary:
   - Phase 0 (Foundation): AIModelConfiguration exists? OrgModelPolicy? waffle flag? model field on session?
   - Phase 1 (ACM-026): Bedrock adapter modules exist? How many of 6?
   - Phase 2 (ACM-025): ModelResolutionService? available_models endpoint?
   - Phase 3 (ACM-024): ModelSelector.vue? useModelSelection.ts?
   - Phase 4 (ACM-023): IsSessionOwnerOrReadOnly? mine filter?
   - Test coverage: X of 78 planned tests written
