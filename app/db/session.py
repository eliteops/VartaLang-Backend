"""SQLAlchemy engine and session factory.

Tuned for Neon Postgres (hosted). Neon suspends idle computes, so we enable
`pool_pre_ping` and a short `pool_recycle` to avoid stale connections
("SSL SYSCALL error: EOF detected"). When the pooled (PgBouncer) endpoint is
used, server-side prepared statements are disabled via `prepare_threshold=None`.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()


def _connect_args() -> dict[str, object]:
    """Extra DBAPI connect arguments, only for the psycopg (v3) Postgres driver."""
    if _settings.database_url.startswith("postgresql+psycopg"):
        # PgBouncer (Neon pooled endpoint) runs in transaction mode, where
        # server-side prepared statements are unsafe. Disable them.
        return {"prepare_threshold": None}
    return {}


engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=_connect_args(),
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a request-scoped session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
