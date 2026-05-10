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
    return fs


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
        plugins=sorted(settings["plugins"].keys()),
        mcp=sorted(settings["mcpServers"].keys()),
        permissions=Permissions(
            allow=len(perms["allow"]),
            deny=len(perms["deny"]),
            ask=len(perms["ask"]),
        ),
    )


def scan_all_repos() -> list[Repo]:
    settings = get_settings()
    out: list[Repo] = []
    for i, repo_path in enumerate(settings.repo_paths):
        repo = _scan_one(repo_path, ACCENTS[i % len(ACCENTS)])
        if repo is not None:
            out.append(repo)
    return out


def get_repo_by_id(repo_id: str) -> Repo | None:
    """Targeted scan: only scan the repo whose directory name matches repo_id."""
    settings = get_settings()
    for i, repo_path in enumerate(settings.repo_paths):
        if repo_path.name == repo_id:
            return _scan_one(repo_path, ACCENTS[i % len(ACCENTS)])
    return None


def scan_global() -> GlobalEnvelope:
    settings = get_settings()
    claude_dir = settings.claude_dir
    fs = _file_sizes(claude_dir)
    s = _read_settings_json(claude_dir)
    perms = s["permissions"]

    skills_names = []
    for p in _list_skills(claude_dir / "skills"):
        skills_names.append(p.parent.name if p.name == "SKILL.md" else p.stem)

    return GlobalEnvelope(
        id="global",
        name="~/.claude (global)",
        path=str(claude_dir).replace(str(Path.home()), "~"),
        description="Global Claude Code setup — applies to every repo",
        agents=list(fs.agents.keys()),
        skills=skills_names,
        commands=list(fs.commands.keys()),
        plugins=sorted(s["plugins"].keys()),
        mcp=sorted(s["mcpServers"].keys()),
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
