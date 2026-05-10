"""Optional external integrations — Linear, Langfuse, GitHub.

Each adapter checks for its required env vars and quietly returns None when
credentials are missing. The frontend doesn't need to know whether any of
these are configured; the data either appears or it doesn't.

Wire format: each adapter returns a dict with fields the frontend already
understands (e.g. {ticket: 'ACM-026', title: '...', url: '...'}).
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

LINEAR_TICKET_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,7}-\d+)\b")


# ---------------------------------------------------------------------------
# Linear — derive a ticket id from the branch name, fetch its title.
# ---------------------------------------------------------------------------

async def linear_ticket_for_branch(branch: str) -> dict | None:
    """Return {ticket, title, url} or None if disabled/missing/unmatched."""
    token = os.getenv("LINEAR_API_KEY")
    if not token or not branch:
        return None
    m = LINEAR_TICKET_RE.search(branch)
    if not m:
        return None
    ticket = m.group(1)
    query = """
    query($id: String!) {
      issue(id: $id) { identifier title url state { name } }
    }
    """
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                "https://api.linear.app/graphql",
                json={"query": query, "variables": {"id": ticket}},
                headers={"Authorization": token},
            )
            if res.status_code != 200:
                return None
            data = res.json().get("data", {}).get("issue")
            if not data:
                return None
            return {
                "ticket": data["identifier"],
                "title": data["title"],
                "url": data["url"],
                "state": (data.get("state") or {}).get("name"),
            }
    except Exception as e:  # noqa: BLE001
        logger.debug("linear lookup failed for %s: %s", ticket, e)
        return None


# ---------------------------------------------------------------------------
# Langfuse — backfill cost from traces matched on session id.
# ---------------------------------------------------------------------------

async def langfuse_cost_for_session(session_id: str) -> dict | None:
    """Return {tokens, cost} or None if disabled/missing/no match."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not public_key or not secret_key or not session_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=4.0, auth=(public_key, secret_key)) as client:
            res = await client.get(
                f"{host}/api/public/sessions/{session_id}",
            )
            if res.status_code != 200:
                return None
            j = res.json()
            return {
                "tokens": int(j.get("totalTokens", 0)),
                "cost": float(j.get("totalCost", 0)),
            }
    except Exception as e:  # noqa: BLE001
        logger.debug("langfuse lookup failed for %s: %s", session_id, e)
        return None


# ---------------------------------------------------------------------------
# GitHub — get the latest PR for a branch via the gh CLI (no token needed
# beyond what `gh auth login` already configured).
# ---------------------------------------------------------------------------

def github_pr_for_branch(repo_path: Path, branch: str) -> dict | None:
    """Return {number, title, url, state} or None."""
    if not branch or branch == "main":
        return None
    try:
        out = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--json",
                "number,title,url,state",
                "--limit",
                "1",
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if out.returncode != 0:
            return None
        import json as _json

        items = _json.loads(out.stdout or "[]")
        return items[0] if items else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None
