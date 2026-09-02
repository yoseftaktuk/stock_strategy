import logging
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import Settings
from app.database.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine(database_url: str) -> Engine:
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        logger.debug("SQLAlchemy engine created")
        return engine
    except Exception as exc:
        raise DatabaseConnectionError("Failed to create database engine") from exc


def get_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = get_engine(settings.database_url)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session(settings: Settings) -> Generator[Session, None, None]:
    session_factory = get_session_factory(settings)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def create_session(settings: Settings) -> Session:
    return get_session_factory(settings)()


def ensure_database_available(settings: Settings) -> None:
    """Open a real connection so import fails fast if PostgreSQL is down."""
    try:
        engine = get_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseConnectionError:
        raise
    except Exception as exc:
        raise DatabaseConnectionError(
            f"PostgreSQL is not available at {settings.postgres_host}:{settings.postgres_port}. "
            "Start it with: docker compose up postgres -d"
        ) from exc


@contextmanager
def session_scope(settings: Settings) -> Generator[Session, None, None]:
    session = create_session(settings)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
