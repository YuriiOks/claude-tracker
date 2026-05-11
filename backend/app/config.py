"""Pydantic Settings — loaded from env / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    claude_dir: Path = Field(default=Path("~/.claude").expanduser())
    repo_roots: str = Field(default="")
    db_path: Path = Field(default=Path("./.cache/tracker.db"))

    host: str = "127.0.0.1"
    port: int = 8765
    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    # Host's home directory. Used to translate JSONL host paths
    # (e.g. /Users/yurii_jupus/...) → container paths (/host/home/...)
    # so repo matching works across the docker boundary. Bare-metal: empty.
    host_home: str = ""

    @field_validator("claude_dir", "db_path", mode="before")
    @classmethod
    def _expand_path(cls, v):  # noqa: ANN001
        if isinstance(v, str):
            return Path(v).expanduser()
        return v

    @property
    def repo_paths(self) -> list[Path]:
        return [Path(p.strip()).expanduser() for p in self.repo_roots.split(",") if p.strip()]

    def translate_host_path(self, host_path: str | Path) -> Path:
        """Translate a host filesystem path → equivalent container path.

        Example with HOST_HOME=/Users/yurii_jupus and the host mount at /host/home:
            /Users/yurii_jupus/Documents/foo → /host/home/Documents/foo

        Bare-metal (no HOST_HOME): returns the path unchanged.
        """
        p = str(host_path)
        if self.host_home and p.startswith(self.host_home):
            return Path("/host/home" + p[len(self.host_home):])
        return Path(p)

    @property
    def projects_dir(self) -> Path:
        return self.claude_dir / "projects"

    @property
    def cost_log(self) -> Path:
        return self.claude_dir / "cost-tracker.log"


@lru_cache
def get_settings() -> Settings:
    return Settings()
