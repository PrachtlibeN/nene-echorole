from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.core.config import REPOSITORY_ROOT, get_settings


def build_engine(database_url: str | None = None) -> Engine:
    url = make_url(database_url or get_settings().echorole_db_url)
    if (
        url.drivername.startswith("sqlite")
        and url.database is not None
        and url.database not in ("", ":memory:")
    ):
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = REPOSITORY_ROOT / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(database_path))

    connect_args = {"check_same_thread": False} if url.drivername.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)

    if url.drivername.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragmas(connection: Any, record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return build_engine()


@lru_cache(maxsize=1)
def get_db_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        factory = get_db_session_factory()
    with factory() as session:
        yield session
