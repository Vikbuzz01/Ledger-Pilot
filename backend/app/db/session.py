"""Configured SQL Server or version-checked portable SQLite engine."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base

SQLITE_SCHEMA_VERSION = "20261101_0006"


@lru_cache
def get_engine() -> Engine:
    """Create the configured engine and safely initialize a new SQLite demo database."""
    settings = get_settings()
    if settings.database_mode == "sqlite":
        path = settings.resolved_sqlite_path
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(path)),
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        try:
            _initialize_sqlite_schema(engine)
        except Exception:
            engine.dispose()
            raise
        return engine
    assert settings.database_url is not None
    return create_engine(
        settings.database_url.get_secret_value(), pool_pre_ping=True, pool_recycle=1800
    )


def _initialize_sqlite_schema(engine: Engine) -> None:
    """Initialize only an empty demo file; fail closed on unknown or old schemas."""
    # Import modules so every mapped table is registered before create_all.
    from app.modules.businesses import models as _businesses  # noqa: F401
    from app.modules.documents import models as _documents  # noqa: F401
    from app.modules.financial_records import models as _financial_records  # noqa: F401
    from app.modules.identity import models as _identity  # noqa: F401
    from app.modules.reconciliation import models as _reconciliation  # noqa: F401

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    marker = "ledgerpilot_schema_info"
    if marker in tables:
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version FROM ledgerpilot_schema_info")
            ).scalar_one_or_none()
        if version != SQLITE_SCHEMA_VERSION:
            raise RuntimeError(
                f"SQLite schema is {version!r}; expected {SQLITE_SCHEMA_VERSION}. "
                "Back up data and use reset-demo-data.bat for disposable demo data."
            )
        missing = set(Base.metadata.tables) - tables
        if missing:
            raise RuntimeError(f"SQLite schema is incomplete; missing tables: {sorted(missing)}")
        return
    if tables:
        raise RuntimeError(
            "SQLite database contains an unrecognized schema. It was not modified; "
            "use a new file or reset-demo-data.bat for disposable demo data."
        )
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.execute(
            text("CREATE TABLE ledgerpilot_schema_info (version VARCHAR(32) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO ledgerpilot_schema_info (version) VALUES (:version)"),
            {"version": SQLITE_SCHEMA_VERSION},
        )


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
