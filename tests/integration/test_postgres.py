"""
Integration tests for PostgreSQL backend.

These tests verify that all models, relationships, constraints, and queries
work correctly against a real PostgreSQL database (not just SQLite).

To run these tests, set the TEST_POSTGRES_URL environment variable:

    # With docker-compose test postgres:
    docker compose -f docker-compose.test.yml up -d
    TEST_POSTGRES_URL=postgresql://nalssi_test:nalssi_test@localhost:5433/nalssi_test uv run pytest tests/integration/test_postgres.py -v

    # Or with any existing PostgreSQL:
    TEST_POSTGRES_URL=postgresql://user:pass@host:5432/testdb uv run pytest tests/integration/test_postgres.py -v
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Alert, Forecast, Location, OutputBackendConfig, WeatherData

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL not set — skipping PostgreSQL tests",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Create a PostgreSQL engine for testing."""
    engine = create_engine(POSTGRES_URL)
    # Drop and recreate all tables for a clean slate
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def pg_session(pg_engine):
    """Create a PostgreSQL session that rolls back after each test."""
    Session = sessionmaker(bind=pg_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def location(pg_session):
    """Create and return a persisted Location."""
    loc = Location(
        name="Portland, OR",
        slug=f"portland_or_{uuid.uuid4().hex[:6]}",
        latitude=45.5152,
        longitude=-122.6784,
        timezone="America/Los_Angeles",
        country_code="US",
        enabled=True,
        collection_interval=300,
        preferred_api="noaa",
    )
    pg_session.add(loc)
    pg_session.commit()
    return loc


# ---------------------------------------------------------------------------
# Connection & dialect
# ---------------------------------------------------------------------------


class TestPostgresConnection:
    def test_can_connect(self, pg_engine):
        """Verify we can connect and the dialect is postgresql."""
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        assert pg_engine.dialect.name == "postgresql"

    def test_uuid_native_type(self, pg_engine):
        """UUID columns should use native PostgreSQL UUID type."""
        from sqlalchemy import inspect

        inspector = inspect(pg_engine)
        columns = {c["name"]: c for c in inspector.get_columns("locations")}
        # PostgreSQL should report UUID type, not NUMERIC like SQLite
        assert "UUID" in str(columns["id"]["type"]).upper()


# ---------------------------------------------------------------------------
# Location CRUD
# ---------------------------------------------------------------------------


class TestLocationCRUD:
    def test_create_location(self, pg_session):
        loc = Location(
            name="Seattle, WA",
            slug="seattle_wa",
            latitude=47.6062,
            longitude=-122.3321,
            country_code="US",
        )
        pg_session.add(loc)
        pg_session.commit()

        assert loc.id is not None
        assert isinstance(loc.id, uuid.UUID)
        assert loc.created_at is not None
        assert loc.updated_at is not None

    def test_read_location(self, pg_session, location):
        fetched = pg_session.get(Location, location.id)
        assert fetched is not None
        assert fetched.name == "Portland, OR"
        assert fetched.latitude == pytest.approx(45.5152)

    def test_update_location(self, pg_session, location):
        location.name = "Portland, Oregon"
        pg_session.commit()
        pg_session.refresh(location)
        assert location.name == "Portland, Oregon"

    def test_delete_location(self, pg_session, location):
        loc_id = location.id
        pg_session.delete(location)
        pg_session.commit()
        assert pg_session.get(Location, loc_id) is None

    def test_latitude_check_constraint(self, pg_session):
        loc = Location(
            name="Invalid", latitude=100.0, longitude=0.0, country_code="US"
        )
        pg_session.add(loc)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_longitude_check_constraint(self, pg_session):
        loc = Location(
            name="Invalid", latitude=0.0, longitude=200.0, country_code="US"
        )
        pg_session.add(loc)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_slug_unique_constraint(self, pg_session):
        slug = f"unique_test_{uuid.uuid4().hex[:6]}"
        loc1 = Location(
            name="A", slug=slug, latitude=0.0, longitude=0.0, country_code="US"
        )
        pg_session.add(loc1)
        pg_session.commit()

        loc2 = Location(
            name="B", slug=slug, latitude=1.0, longitude=1.0, country_code="US"
        )
        pg_session.add(loc2)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_collection_interval_check(self, pg_session):
        loc = Location(
            name="Bad interval",
            latitude=0.0,
            longitude=0.0,
            country_code="US",
            collection_interval=0,
        )
        pg_session.add(loc)
        with pytest.raises(IntegrityError):
            pg_session.commit()


# ---------------------------------------------------------------------------
# WeatherData
# ---------------------------------------------------------------------------


class TestWeatherData:
    def test_create_weather_data(self, pg_session, location):
        weather = WeatherData(
            location_id=location.id,
            source_api="noaa",
            temperature=22.5,
            temperature_fahrenheit=72.5,
            humidity=55,
            pressure=1015.0,
            wind_speed=3.2,
            condition_code="clear",
            condition_text="Clear",
        )
        pg_session.add(weather)
        pg_session.commit()

        assert weather.id is not None
        assert isinstance(weather.id, uuid.UUID)
        assert weather.temperature == pytest.approx(22.5)

    def test_weather_foreign_key(self, pg_session):
        """Weather data with non-existent location_id should fail."""
        weather = WeatherData(
            location_id=uuid.uuid4(),
            source_api="noaa",
            temperature=20.0,
        )
        pg_session.add(weather)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_cascade_delete(self, pg_session):
        """Deleting a location should cascade-delete its weather data."""
        loc = Location(
            name="Temp City",
            latitude=10.0,
            longitude=10.0,
            country_code="US",
        )
        pg_session.add(loc)
        pg_session.commit()

        weather = WeatherData(
            location_id=loc.id, source_api="noaa", temperature=15.0
        )
        pg_session.add(weather)
        pg_session.commit()
        weather_id = weather.id

        pg_session.delete(loc)
        pg_session.commit()
        assert pg_session.get(WeatherData, weather_id) is None

    def test_weather_relationship(self, pg_session, location):
        for i in range(3):
            pg_session.add(
                WeatherData(
                    location_id=location.id,
                    source_api="open-meteo",
                    temperature=18.0 + i,
                )
            )
        pg_session.commit()
        pg_session.refresh(location)
        assert len(location.weather_data) == 3

    def test_timezone_aware_timestamps(self, pg_session, location):
        """PostgreSQL should preserve timezone info on datetime columns."""
        specific_time = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        weather = WeatherData(
            location_id=location.id,
            source_api="noaa",
            timestamp=specific_time,
            temperature=25.0,
        )
        pg_session.add(weather)
        pg_session.commit()
        pg_session.refresh(weather)

        assert weather.timestamp.tzinfo is not None
        assert weather.timestamp == specific_time


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    def _make_alert(self, location_id, alert_id="ALERT-001", **kwargs):
        now = datetime.now(UTC)
        defaults = dict(
            location_id=location_id,
            alert_id=alert_id,
            source_api="noaa",
            event="High Wind Warning",
            headline="Winds up to 60 mph expected",
            severity="Severe",
            urgency="Immediate",
            certainty="Likely",
            effective=now,
            expires=now + timedelta(hours=6),
        )
        defaults.update(kwargs)
        return Alert(**defaults)

    def test_create_alert(self, pg_session, location):
        alert = self._make_alert(location.id)
        pg_session.add(alert)
        pg_session.commit()

        assert alert.id is not None
        assert isinstance(alert.id, uuid.UUID)
        assert alert.event == "High Wind Warning"

    def test_alert_dedup_constraint(self, pg_session, location):
        """Same (location_id, alert_id, source_api) should be rejected."""
        dedup_id = f"DEDUP-{uuid.uuid4().hex[:6]}"
        a1 = self._make_alert(location.id, alert_id=dedup_id)
        pg_session.add(a1)
        pg_session.commit()

        a2 = self._make_alert(location.id, alert_id=dedup_id)
        pg_session.add(a2)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_alert_cascade_delete(self, pg_session):
        loc = Location(
            name="Alert City", latitude=30.0, longitude=-90.0, country_code="US"
        )
        pg_session.add(loc)
        pg_session.commit()

        alert = self._make_alert(loc.id, alert_id="CASCADE-TEST")
        pg_session.add(alert)
        pg_session.commit()
        alert_id = alert.id

        pg_session.delete(loc)
        pg_session.commit()
        assert pg_session.get(Alert, alert_id) is None

    def test_alert_cap_fields(self, pg_session, location):
        alert = self._make_alert(
            location.id,
            alert_id=f"CAP-{uuid.uuid4().hex[:6]}",
            category="Met",
            response_type="Shelter",
            sender_name="NWS Portland OR",
            status="Actual",
            message_type="Alert",
            onset=datetime.now(UTC),
            ends=datetime.now(UTC) + timedelta(hours=12),
            areas=json.dumps(["Multnomah County", "Washington County"]),
            description="Damaging winds expected.",
            instruction="Secure outdoor objects.",
        )
        pg_session.add(alert)
        pg_session.commit()
        pg_session.refresh(alert)

        assert alert.category == "Met"
        assert alert.sender_name == "NWS Portland OR"
        assert json.loads(alert.areas) == ["Multnomah County", "Washington County"]

    def test_alert_relationship(self, pg_session, location):
        for i in range(2):
            pg_session.add(
                self._make_alert(
                    location.id, alert_id=f"REL-{uuid.uuid4().hex[:6]}"
                )
            )
        pg_session.commit()
        pg_session.refresh(location)
        assert len(location.alerts) >= 2


# ---------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------


class TestForecasts:
    def _make_forecast(self, location_id, offset_hours=0, **kwargs):
        now = datetime.now(UTC)
        start = now + timedelta(hours=offset_hours)
        defaults = dict(
            location_id=location_id,
            source_api="noaa",
            start_time=start,
            end_time=start + timedelta(hours=12),
            temperature=25.0,
            temperature_fahrenheit=77.0,
            humidity=50,
            wind_speed=4.0,
            condition_text="Mostly Sunny",
            is_daytime=True,
        )
        defaults.update(kwargs)
        return Forecast(**defaults)

    def test_create_forecast(self, pg_session, location):
        fc = self._make_forecast(location.id)
        pg_session.add(fc)
        pg_session.commit()

        assert fc.id is not None
        assert isinstance(fc.id, uuid.UUID)
        assert fc.temperature == pytest.approx(25.0)

    def test_forecast_dedup_constraint(self, pg_session, location):
        """Same (location_id, source_api, start_time) should be rejected."""
        start = datetime(2025, 7, 1, 12, 0, 0, tzinfo=UTC)
        f1 = self._make_forecast(location.id, start_time=start)
        pg_session.add(f1)
        pg_session.commit()

        f2 = self._make_forecast(location.id, start_time=start)
        pg_session.add(f2)
        with pytest.raises(IntegrityError):
            pg_session.commit()

    def test_forecast_cascade_delete(self, pg_session):
        loc = Location(
            name="Forecast City", latitude=40.0, longitude=-80.0, country_code="US"
        )
        pg_session.add(loc)
        pg_session.commit()

        fc = self._make_forecast(loc.id)
        pg_session.add(fc)
        pg_session.commit()
        fc_id = fc.id

        pg_session.delete(loc)
        pg_session.commit()
        assert pg_session.get(Forecast, fc_id) is None

    def test_forecast_relationship(self, pg_session, location):
        for i in range(3):
            pg_session.add(self._make_forecast(location.id, offset_hours=i * 12))
        pg_session.commit()
        pg_session.refresh(location)
        assert len(location.forecasts) >= 3

    def test_forecast_detailed_fields(self, pg_session, location):
        fc = self._make_forecast(
            location.id,
            offset_hours=100,
            detailed_forecast="Sunny with a high near 77. Light winds.",
            precipitation_probability=10,
            precipitation_amount=0.5,
            pressure=1012.0,
            cloud_cover=20,
            uv_index=6.5,
        )
        pg_session.add(fc)
        pg_session.commit()
        pg_session.refresh(fc)

        assert fc.detailed_forecast.startswith("Sunny")
        assert fc.precipitation_probability == 10
        assert fc.uv_index == pytest.approx(6.5)


# ---------------------------------------------------------------------------
# OutputBackendConfig
# ---------------------------------------------------------------------------


class TestOutputBackendConfig:
    def test_create_backend_config(self, pg_session):
        config = OutputBackendConfig(
            name="Test Redis",
            backend_type="redis",
            enabled=True,
            connection_config=json.dumps({"url": "redis://localhost:6379/0"}),
            format_type="kurokku",
            write_timeout=10,
            retry_count=1,
        )
        pg_session.add(config)
        pg_session.commit()

        assert config.id is not None
        assert isinstance(config.id, uuid.UUID)
        parsed = json.loads(config.connection_config)
        assert parsed["url"] == "redis://localhost:6379/0"

    def test_backend_config_defaults(self, pg_session):
        config = OutputBackendConfig(
            name="Minimal",
            backend_type="influxdb",
            connection_config="{}",
        )
        pg_session.add(config)
        pg_session.commit()

        assert config.enabled is True
        assert config.write_timeout == 10
        assert config.retry_count == 1
        assert config.format_type is None
        assert config.location_filter is None

    def test_backend_config_with_location_filter(self, pg_session):
        config = OutputBackendConfig(
            name="Filtered",
            backend_type="redis",
            connection_config="{}",
            location_filter=json.dumps({"include": ["portland_or"]}),
        )
        pg_session.add(config)
        pg_session.commit()
        pg_session.refresh(config)

        parsed = json.loads(config.location_filter)
        assert parsed == {"include": ["portland_or"]}


# ---------------------------------------------------------------------------
# Alembic migrations
# ---------------------------------------------------------------------------


class TestAlembicMigrations:
    def test_migrations_against_postgres(self, pg_engine):
        """
        Verify that Alembic migrations can run cleanly against PostgreSQL.

        This catches migration SQL that works on SQLite but not PostgreSQL
        (e.g., ALTER TABLE quirks, type differences).
        """
        from alembic import command
        from alembic.config import Config

        from app.config import settings

        # Drop all tables (including alembic_version) so migrations start fresh
        Base.metadata.drop_all(bind=pg_engine)
        with pg_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
            conn.commit()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", POSTGRES_URL)

        # env.py reads settings.DATABASE_URL which overrides alembic.ini.
        # Temporarily bypass the frozen Pydantic model to point at postgres.
        original_url = settings.DATABASE_URL
        try:
            object.__setattr__(settings, "DATABASE_URL", POSTGRES_URL)
            command.upgrade(alembic_cfg, "head")
        finally:
            object.__setattr__(settings, "DATABASE_URL", original_url)

        # Verify tables exist by querying them
        with pg_engine.connect() as conn:
            for table in [
                "locations",
                "weather_data",
                "alerts",
                "forecasts",
                "output_backend_configs",
            ]:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                assert result.scalar() == 0  # Tables exist and are empty

        # Recreate via metadata for remaining tests
        Base.metadata.drop_all(bind=pg_engine)
        with pg_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
            conn.commit()
        Base.metadata.create_all(bind=pg_engine)
