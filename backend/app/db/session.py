"""SQL Server engine and request-scoped session factory."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the SQL Server engine lazily so health checks don't require DB startup."""
    database_url = get_settings().database_url.get_secret_value()
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a session and always close it after the request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
