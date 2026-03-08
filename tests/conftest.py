"""
Pytest configuration and shared fixtures.
"""

import json
import os
from pathlib import Path

# IMPORTANT: Set test environment variables BEFORE importing app modules
# This ensures the app uses test configuration, not production
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///./test_nalssi.db"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_artifacts():
    """
    Clean up any test database files that may have been created.

    Note: Tests use :memory: by default, but this cleans up any
    accidental file-based test databases.
    """
    test_db_files = [
        Path(__file__).parent.parent / "test_nalssi.db",
        Path(__file__).parent.parent / "test.db",
    ]

    # Clean up before tests
    for db_file in test_db_files:
        if db_file.exists():
            db_file.unlink()

    yield

    # Clean up after tests
    for db_file in test_db_files:
        if db_file.exists():
            db_file.unlink()


@pytest.fixture(scope="session", autouse=True)
def verify_test_mode():
    """
    Verify that we're not accidentally using the production database.
    """
    from app.config import settings

    # Ensure we're not using production database
    prod_db_paths = [
        "sqlite:///./nalssi.db",
        "sqlite:///nalssi.db",
        "sqlite:////app/data/nalssi.db",
    ]
    if settings.DATABASE_URL in prod_db_paths:
        raise RuntimeError(
            f"Tests are configured to use production database: {settings.DATABASE_URL}\n"
            f"This is dangerous! Tests should use :memory: for isolation."
        )

    print(f"\n✓ Tests using database: {settings.DATABASE_URL}")
    print(f"✓ Scheduler disabled: {not settings.ENABLE_SCHEDULER}")
    print(f"✓ Test database will be cleaned up after tests")

    return settings


@pytest.fixture(scope="session", autouse=True)
def create_app_tables():
    """
    Create tables in the app's database engine.

    This is needed for integration tests that use the FastAPI test client,
    which uses the app's database engine (not the test db_engine fixture).
    """
    from app.database import engine, Base

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_engine():
    """
    Create an in-memory SQLite database for testing.
    Each test gets a fresh database.
    """
    from sqlalchemy import event

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """
    Create a database session for testing.
    Automatically rolls back after each test.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_location_data():
    """Sample location data for testing."""
    return {
        "name": "San Francisco, CA",
        "slug": "san_francisco_ca",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "timezone": "America/Los_Angeles",
        "country_code": "US",
        "enabled": True,
        "collection_interval": 300,
        "preferred_api": "noaa",
    }


@pytest.fixture
def sample_weather_data():
    """Sample weather data for testing."""
    return {
        "temperature": 18.5,
        "temperature_fahrenheit": 65.3,
        "feels_like": 17.2,
        "humidity": 65,
        "pressure": 1013.25,
        "wind_speed": 5.5,
        "wind_direction": 270,
        "wind_gust": 8.2,
        "precipitation": 0.0,
        "cloud_cover": 40,
        "visibility": 10000,
        "uv_index": 3,
        "condition_code": "partly_cloudy",
        "condition_text": "Partly Cloudy",
        "icon": "02d",
    }


@pytest.fixture
def sample_backend_config_data():
    """Sample backend config data for testing."""
    return {
        "name": "Test Redis",
        "backend_type": "redis",
        "enabled": True,
        "connection_config": {"url": "redis://localhost:6379/0"},
        "format_type": "kurokku",
        "format_config": None,
        "location_filter": None,
        "write_timeout": 10,
        "retry_count": 1,
    }


@pytest.fixture
def noaa_responses():
    """Load NOAA API response fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "noaa_responses.json"
    with open(fixtures_path) as f:
        return json.load(f)
