"""Walk a repo's .claude/ folder and produce a Repo schema."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import get_settings
from app.schemas.inventory import FileSizes, GlobalEnvelope, PermissionsDetail
from app.schemas.repo import Permissions, Repo, RepoStats
from app.services.fs_utils import git_branch, list_files, list_md_files

logger = logging.getLogger(__name__)

ACCENTS = ["#d97757", "#5a8dee", "#a78bfa", "#10b981", "#f59e0b", "#ef4444"]

# Project-root files Claude Code reads at session start, plus repo
# conventions we surface in the dashboard. Order = display order.
ROOT_FILES = (
    "CLAUDE.md",
    ".mcp.json",
    ".worktreeinclude",
    "ERRORS.md",
    "MASTER_PLAN.md",
)


def _read_settings_json(claude_dir: Path) -> dict:
    merged: dict = {
        "permissions": {"allow": [], "deny": [], "ask": []},
        "plugins": {},
        "mcpServers": {},
    }
    for name in ("settings.json", "settings.local.json"):
        p = claude_dir / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception as e:
            logger.warning("could not parse %s: %s", p, e)
            continue
        for bucket in ("allow", "deny", "ask"):
            merged["permissions"][bucket].extend(
                data.get("permissions", {}).get(bucket, []) or []
            )
        merged["plugins"].update(data.get("plugins", {}) or {})
        merged["mcpServers"].update(data.get("mcpServers", {}) or {})
    return merged


def _list_skills(skills_dir: Path) -> list[Path]:
    if not skills_dir.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(skills_dir.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            out.append(child / "SKILL.md")
        elif child.is_file() and child.suffix == ".md":
            out.append(child)
    return out


def _list_agent_memory(mem_dir: Path) -> list[Path]:
    """agent-memory/<agent-name>/MEMORY.md — one entry per agent that has memory."""
    if not mem_dir.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(mem_dir.iterdir()):
        if child.is_dir() and (child / "MEMORY.md").is_file():
            out.append(child / "MEMORY.md")
    return out


def _file_sizes(claude_dir: Path) -> FileSizes:
    fs = FileSizes()
    for p in list_md_files(claude_dir / "agents"):
        fs.agents[p.stem] = p.stat().st_size
    for p in _list_skills(claude_dir / "skills"):
        name = p.parent.name if p.name == "SKILL.md" else p.stem
        fs.skills[name] = p.stat().st_size
    for p in list_md_files(claude_dir / "commands"):
        fs.commands[f"/{p.stem}"] = p.stat().st_size
    for p in list_md_files(claude_dir / "rules"):
        fs.rules[p.stem] = p.stat().st_size
    for p in list_files(claude_dir / "hooks", (".sh", ".py", ".js")):
        fs.hooks[p.name] = p.stat().st_size
    for p in list_md_files(claude_dir / "output-styles"):
        fs.output_styles[p.stem] = p.stat().st_size
    for p in _list_agent_memory(claude_dir / "agent-memory"):
        # Display the agent name, not the MEMORY.md leaf.
        fs.agent_memory[p.parent.name] = p.stat().st_size
    for p in list_md_files(claude_dir / "contexts"):
        fs.contexts[p.stem] = p.stat().st_size
    return fs


def _scan_root_files(repo_path: Path) -> list[str]:
    """Return the subset of ROOT_FILES that actually exist at repo root."""
    return [name for name in ROOT_FILES if (repo_path / name).exists()]


def _scan_one(repo_path: Path, accent: str) -> Repo | None:
    if not repo_path.is_dir():
        logger.info("repo path missing: %s", repo_path)
        return None
    claude_dir = repo_path / ".claude"
    fs = _file_sizes(claude_dir)
    settings = _read_settings_json(claude_dir)
    perms = settings["permissions"]

    skills_names = []
    for p in _list_skills(claude_dir / "skills"):
        skills_names.append(p.parent.name if p.name == "SKILL.md" else p.stem)

    return Repo(
        id=repo_path.name,
        name=repo_path.name,
        org="personal",
        path=str(repo_path).replace(str(Path.home()), "~"),
        description="",
        branch=git_branch(repo_path),
        language="",
        accent=accent,
        is_active=False,
        stats=RepoStats(),
        agents=list(fs.agents.keys()),
        skills=skills_names,
        commands=list(fs.commands.keys()),
        rules=list(fs.rules.keys()),
        hooks=list(fs.hooks.keys()),
        output_styles=list(fs.output_styles.keys()),
        agent_memory=list(fs.agent_memory.keys()),
        contexts=list(fs.contexts.keys()),
        plugins=sorted(settings["plugins"].keys()),
        mcp=sorted(settings["mcpServers"].keys()),
        root_files=_scan_root_files(repo_path),
        permissions=Permissions(
            allow=len(perms["allow"]),
            deny=len(perms["deny"]),
            ask=len(perms["ask"]),
        ),
    )


def scan_all_repos() -> list[Repo]:
    from app.services.repo_registry import all_repo_paths
    out: list[Repo] = []
    for i, repo_path in enumerate(all_repo_paths()):
        repo = _scan_one(repo_path, ACCENTS[i % len(ACCENTS)])
        if repo is not None:
            out.append(repo)
    return out


def get_repo_by_id(repo_id: str) -> Repo | None:
    """Targeted scan: only scan the repo whose directory name matches repo_id."""
    from app.services.repo_registry import all_repo_paths
    for i, repo_path in enumerate(all_repo_paths()):
        if repo_path.name == repo_id:
            return _scan_one(repo_path, ACCENTS[i % len(ACCENTS)])
    return None


def _read_claude_json_mcp(path: Path) -> set[str]:
    """Return the set of MCP server names from a .claude.json at `path`.

    Claude Code stores its long-lived mcpServers config at the top level
    of ~/.claude.json (not in ~/.claude/settings.json). Caller passes the
    resolved path so this works for both bare-metal (~/.claude.json) and
    Docker (/host/home/.claude.json via the home bind mount). Missing or
    malformed file falls back to an empty set so /api/global never 500s.
    """
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return set()
    mcp = data.get("mcpServers", {}) or {}
    return set(mcp.keys()) if isinstance(mcp, dict) else set()


def _claude_json_path() -> Path:
    """Resolve the path to .claude.json reachable from this process.

    Under Docker, the host's ~/.claude.json is mounted into /host/home —
    `settings.translate_host_path` rewrites the host path accordingly.
    Bare-metal: returns ~/.claude.json directly.
    """
    settings = get_settings()
    if settings.host_home:
        return settings.translate_host_path(Path(settings.host_home) / ".claude.json")
    return Path.home() / ".claude.json"


def scan_global() -> GlobalEnvelope:
    settings = get_settings()
    claude_dir = settings.claude_dir
    fs = _file_sizes(claude_dir)
    s = _read_settings_json(claude_dir)
    perms = s["permissions"]

    skills_names = []
    for p in _list_skills(claude_dir / "skills"):
        skills_names.append(p.parent.name if p.name == "SKILL.md" else p.stem)

    # Plugins: sourced from ~/.claude/plugins/installed_plugins.json
    # (managed by the /plugin CLI), not settings.json — the latter is
    # almost always empty even when many plugins are installed.
    plugin_names = collect_plugins_dict().get("names", [])

    # MCP: union of ~/.claude.json (canonical legacy location used by
    # Claude Code) + ~/.claude/settings.json mcpServers (newer override).
    # Dedupe + sort so the rendered list is stable.
    mcp_names = sorted(
        set(s["mcpServers"].keys()) | _read_claude_json_mcp(_claude_json_path())
    )

    return GlobalEnvelope(
        id="global",
        name="~/.claude (global)",
        path=str(claude_dir).replace(str(Path.home()), "~"),
        description="Global Claude Code setup — applies to every repo",
        agents=list(fs.agents.keys()),
        skills=skills_names,
        commands=list(fs.commands.keys()),
        rules=list(fs.rules.keys()),
        hooks=list(fs.hooks.keys()),
        output_styles=list(fs.output_styles.keys()),
        agent_memory=list(fs.agent_memory.keys()),
        plugins=plugin_names,
        mcp=mcp_names,
        permissions=Permissions(
            allow=len(perms["allow"]),
            deny=len(perms["deny"]),
            ask=len(perms["ask"]),
        ),
        file_sizes=fs,
    )


def collect_permissions_detail() -> PermissionsDetail:
    settings = get_settings()
    detail = PermissionsDetail()
    sources = [settings.claude_dir]
    sources.extend(p / ".claude" for p in settings.repo_paths)
    for d in sources:
        merged = _read_settings_json(d)
        for bucket in ("allow", "deny", "ask"):
            for rule in merged["permissions"][bucket]:
                bucket_list = getattr(detail, bucket)
                if rule not in bucket_list:
                    bucket_list.append(rule)
    return detail


def collect_plugins_dict() -> dict:
    settings = get_settings()
    p = settings.claude_dir / "plugins" / "installed_plugins.json"
    if not p.is_file():
        return {"version": 0, "plugins": {}, "names": []}
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        logger.warning("plugins manifest unreadable: %s", e)
        return {"version": 0, "plugins": {}, "names": []}
    data["names"] = sorted(data.get("plugins", {}).keys())
    return data
