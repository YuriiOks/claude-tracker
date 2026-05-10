---
paths:
  - "spa-frontend/**/*.ts"
  - "spa-frontend/**/*.vue"
  - "frontend/**/*.ts"
  - "frontend/**/*.vue"
---

# Frontend Conventions

## Stack
- Vue 3 Composition API (`<script setup lang="ts">`)
- Pinia for state management
- TypeScript strict mode
- pnpm as package manager (not npm/yarn)

## API Types
- Auto-generated from Django serializers via `./generate_types.sh`
- Run after any model or serializer change
- Never hand-write API response types — regenerate instead

## Component Patterns
- Use `<script setup>` syntax, not Options API
- Props: use `defineProps<{...}>()` with TypeScript interface
- Emits: use `defineEmits<{...}>()`
- Composables in `composables/` directory with `use` prefix

## Linting
```bash
pnpm run lint          # ESLint
pnpm run type-check    # TypeScript
pnpm run format        # Prettier
```
