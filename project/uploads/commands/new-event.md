---
description: Scaffold a new distributed event and observer
---

Create a new event and observer for: $ARGUMENTS

Steps:
1. Parse arguments to determine: Django app name, event name, event data fields
2. Create or update `app/{app}/events.py`:
   - Add Event class inheriting from `events.events.event.Event`
   - Add nested `EventData(BaseModel)` with specified fields
   - Use PascalCase ending with `Event`
3. Create or update `app/{app}/observers.py`:
   - Add Observer class inheriting from `events.observers.observer.Observer`
   - Set `events = [NewEvent]`
   - Add `run()` method with isinstance check
4. Verify auto-discovery: check that `event_registry.py` will find the new files
5. Report: files created/modified, event name, observer name

Example: `/new-event cases CaseCreated case_uuid:str case_type:str org_uuid:str`
