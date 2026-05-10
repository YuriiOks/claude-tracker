---
description: Build Vue action widgets for AI agent actions. Use when creating frontend UI for reviewing and modifying AI-proposed actions.
effort: high
---

# Jupus Action Widgets (Vue)

Every `CommitableAgentAction` on the backend needs a corresponding Vue widget for user review.

## Directory

`spa-frontend/src/components/agent-actions/widgets/`

## Creating a Widget

```vue
<script lang="ts" setup>
import { ref, watch } from 'vue'
import type { TAgentAction } from '@/types/generated'

const props = defineProps<{
  action: TAgentAction
  customPayload?: Record<string, any>
}>()

const emit = defineEmits<{
  payloadChanged: [payload: Record<string, any>]
}>()

const localStatus = ref(props.action.payload.new_status)

watch(localStatus, (val) => {
  emit('payloadChanged', { ...props.action.payload, new_status: val })
})

const isSummary = computed(() =>
  props.action.is_committed || props.action.is_reverted || props.action.has_commit_error
)
</script>

<template>
  <!-- Editable state (pending) -->
  <div v-if="!isSummary">
    Update case status to
    <InlineSelect v-model="localStatus" :options="statusOptions" variant="inline-text" />
  </div>

  <!-- Summary state (committed/reverted) -->
  <div v-else>
    Case status updated to <strong>{{ action.payload.new_status }}</strong>
  </div>
</template>
```

## Register in Widget Map

In `AgentActionWidget.vue`:

```typescript
const actionWidgetMap: Record<string, Component> = {
  'update_case_status': UpdateCaseStatusWidget,
  // ... other widgets
}
```

**Action type key MUST match backend `action_type` exactly.**

## Design Principles

1. **Two-state design**: Editable (pending) vs Summary (committed/reverted)
2. **Natural language flow**: Actions read as coherent sentences ("Update case status to **open**")
3. **Inline form fields**: Use `variant="inline-text"` for fields blending into text
4. **All parameters editable**: Every AI-proposed value must be modifiable by user
5. **Translations**: Use `useTranslation()` with en/de dictionaries

## Type Generation

Run `./generate_types.sh` after adding new action types on backend.
Import types from `@/types/generated`.

## Checklist

- [ ] Widget handles both editable and summary states
- [ ] All AI parameters are editable
- [ ] Skeleton loader for async data
- [ ] Form validation with error display
- [ ] Registered in `actionWidgetMap`
- [ ] Types regenerated after backend changes
