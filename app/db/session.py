from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


_settings = get_settings()


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


_database_url = _normalize_database_url(_settings.database_url)


def _build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite://"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    return create_engine(database_url, echo=False, pool_pre_ping=True, future=True)


_engine: Engine = _build_engine(_database_url)


def get_engine() -> Engine:
    return _engine


def configure_engine(database_url: str) -> None:
    global _database_url, _engine
    _database_url = _normalize_database_url(database_url)
    _engine = _build_engine(_database_url)


def init_db(engine: Optional[Engine] = None) -> None:
    target_engine = engine or _engine
    SQLModel.metadata.create_all(target_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(_engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
