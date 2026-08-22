"""Database bootstrap — engine selected by DATABASE_URL.

Defaults to local SQLite; pointing DATABASE_URL at Supabase/Postgres is a
one-line env change. Avoid SQLite-only SQL everywhere so the swap holds.
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
# SQLite needs check_same_thread=False for the background pipeline task;
# Postgres (Supabase) benefits from pre-ping so dropped idle connections are
# transparently re-established (Render/Railway and poolers cull idle conns).
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=not _is_sqlite,
)


def create_db_and_tables() -> None:
    from . import models  # noqa: F401 — registers table metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
