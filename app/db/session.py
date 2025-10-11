from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings


_settings = get_settings()
_database_url = _settings.database_url
if _database_url.startswith("postgres://"):
    # Normalize legacy scheme to the psycopg driver SQLAlchemy expects.
    _database_url = _database_url.replace("postgres://", "postgresql+psycopg://", 1)

_engine = create_engine(_database_url, echo=False, pool_pre_ping=True)


def init_db() -> None:
    SQLModel.metadata.create_all(_engine)


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
