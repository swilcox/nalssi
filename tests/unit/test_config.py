"""
Unit tests for configuration management.

Following TDD: Write tests first, then implement.
"""

import pytest

from app.config import Settings


@pytest.mark.unit
def test_settings_loads_defaults():
    """Test that settings object loads with default values."""
    settings = Settings()

    assert settings.APP_NAME == "nalssi"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DEBUG is False


@pytest.mark.unit
def test_settings_database_url_default():
    """Test default database URL is SQLite."""
    import os

    # Save current env var
    saved_db_url = os.environ.get("DATABASE_URL")

    try:
        # Remove env var to test default
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        settings = Settings()

        assert "sqlite" in settings.DATABASE_URL
        assert settings.DATABASE_URL.endswith("nalssi.db")
    finally:
        # Restore env var
        if saved_db_url:
            os.environ["DATABASE_URL"] = saved_db_url


@pytest.mark.unit
def test_settings_api_defaults():
    """Test API-related default settings."""
    settings = Settings()

    assert settings.NOAA_API_BASE_URL == "https://api.weather.gov"
    assert settings.OPEN_METEO_API_BASE_URL == "https://api.open-meteo.com/v1"
    assert settings.DEFAULT_COLLECTION_INTERVAL == 300
    assert settings.MAX_CONCURRENT_COLLECTIONS == 5


@pytest.mark.unit
def test_settings_server_defaults():
    """Test server configuration defaults."""
    settings = Settings()

    assert settings.API_HOST == "0.0.0.0"
    assert settings.API_PORT == 8000


@pytest.mark.unit
def test_settings_from_env(monkeypatch):
    """Test that settings can be loaded from environment variables."""
    monkeypatch.setenv("APP_NAME", "test-nalssi")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings()

    assert settings.APP_NAME == "test-nalssi"
    assert settings.DEBUG is True
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.API_PORT == 9000


@pytest.mark.unit
def test_settings_database_url_from_env(monkeypatch):
    """Test that database URL can be overridden via environment."""
    custom_db_url = "postgresql://user:pass@localhost/testdb"
    monkeypatch.setenv("DATABASE_URL", custom_db_url)

    settings = Settings()

    assert custom_db_url == settings.DATABASE_URL


@pytest.mark.unit
def test_settings_validates_collection_interval():
    """Test that collection interval must be positive."""
    # This should work
    settings = Settings(DEFAULT_COLLECTION_INTERVAL=60)
    assert settings.DEFAULT_COLLECTION_INTERVAL == 60

    # This should fail validation
    with pytest.raises(ValueError):
        Settings(DEFAULT_COLLECTION_INTERVAL=-1)


@pytest.mark.unit
def test_settings_validates_port_range():
    """Test that API port is within valid range."""
    # Valid port
    settings = Settings(API_PORT=8080)
    assert settings.API_PORT == 8080

    # Invalid ports should raise ValueError
    with pytest.raises(ValueError):
        Settings(API_PORT=0)

    with pytest.raises(ValueError):
        Settings(API_PORT=70000)


@pytest.mark.unit
def test_settings_optional_services():
    """Test optional service configurations."""
    settings = Settings()

    # These should have defaults or be optional
    assert settings.REDIS_URL == "redis://localhost:6379/0"
    assert settings.INFLUXDB_URL == "http://localhost:8086"
    assert settings.INFLUXDB_TOKEN == ""
    assert settings.INFLUXDB_ORG == ""
    assert settings.INFLUXDB_BUCKET == "weather"


@pytest.mark.unit
def test_settings_immutable():
    """Test that settings are frozen after creation."""
    from pydantic import ValidationError

    settings = Settings()

    # Pydantic settings should be frozen
    with pytest.raises((ValidationError, AttributeError)):
        settings.APP_NAME = "changed"
