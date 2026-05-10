---
paths:
  - "app/**/*.py"
---

# Logging & Error Handling

## Sentry Grouping Rule

Sentry groups issues by log message. Use **static descriptions** with dynamic data in `extra` kwargs.

```python
# GOOD - groups all failures under one Sentry issue
logger.error(
    "Document generation failed",
    extra={"document_id": doc.id, "user_id": user.id, "error": str(e)}
)

# BAD - creates a new Sentry issue per document
logger.error(f"Document generation failed for {doc.id}: {e}")
```

## Pattern

```python
import logging

logger = logging.getLogger(__name__)

# Info: static description + extra
logger.info("Case created", extra={"case_id": case.id, "org_id": org.id})

# Warning: static description + extra
logger.warning("Payment retry scheduled", extra={"payment_id": payment.id, "attempt": attempt})

# Error: static description + extra + capture_exception
try:
    process(item)
except SpecificError as e:
    logger.error("Item processing failed", extra={"item_id": item.id, "error": str(e)})
    capture_exception(e)
    raise
```

## Rules

1. Never interpolate dynamic values into log message strings
2. Use `extra` dict for all variable data (IDs, counts, names)
3. Use `capture_exception(e)` for explicit Sentry error capture
4. No bare `except:` — always catch specific exception types
5. Re-raise after logging unless you have a specific recovery strategy
