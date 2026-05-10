"""SQLAlchemy async engine + session factory."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ensure_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+aiosqlite:///{settings.db_path}"
    _engine = create_async_engine(url, echo=False, future=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    _ensure_engine()
    if _engine is None:
        raise RuntimeError("DB engine not initialized — call await init_db() first")
    # Import models lazily so metadata is populated before create_all.
    # Safe before Phase A3 — the package may not yet contain modules.
    try:
        from app.models import session_event, session_summary  # noqa: F401
    except ImportError:
        pass

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    _ensure_engine()
    if _sessionmaker is None:
        raise RuntimeError("DB sessionmaker not initialized — call await init_db() first")
    async with _sessionmaker() as session:
        yield session
