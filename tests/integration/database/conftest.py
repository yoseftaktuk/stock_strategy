import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.database.session import Base


def _require_psycopg2() -> None:
    try:
        import psycopg2  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip(
            "psycopg2 is not installed for this Python interpreter. "
            f"Activate the project venv first: source .venv/bin/activate "
            f"(current: {sys.executable})"
        )


def pytest_configure(config: pytest.Config) -> None:
    _require_psycopg2()


def _can_connect(database_url: str) -> bool:
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except OperationalError:
        return False


def _ensure_test_database(db_settings: Settings) -> None:
    if _can_connect(db_settings.test_database_url):
        return

    admin_url = db_settings._build_database_url("postgres")
    if not _can_connect(admin_url):
        pytest.skip(
            "PostgreSQL is not available at "
            f"{db_settings.postgres_host}:{db_settings.postgres_port}. "
            "Start it with: POSTGRES_PORT=5433 docker compose up postgres -d "
            "(port 5432 may be used by another container on your machine)."
        )

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        try:
            connection.execute(text(f"CREATE DATABASE {db_settings.postgres_test_db}"))
        except ProgrammingError as exc:
            if "already exists" not in str(exc):
                raise
    admin_engine.dispose()


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def db_engine(db_settings: Settings):
    _ensure_test_database(db_settings)
    database_url = db_settings.test_database_url

    if not _can_connect(database_url):
        pytest.skip("PostgreSQL test database is not available")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, autocommit=False, autoflush=False)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session_committed(db_engine) -> Session:
    session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)()
    yield session
    session.rollback()
    session.close()
