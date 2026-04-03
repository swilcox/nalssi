"""
Tests for weather collector service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from app.models.alert import Alert
from app.models.location import Location
from app.models.weather import WeatherData
from app.services.collectors.weather_collector import WeatherCollector, get_collector
from app.services.weather_apis.base import WeatherAlert, WeatherData as APIWeatherData


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collector_initialization():
    """Test that collector initializes correctly."""
    collector = WeatherCollector()
    assert collector.noaa_client is not None
    assert collector.open_meteo_client is not None
    assert collector.openweather_client is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_for_location_us(db_session):
    """Test collecting weather for a US location."""
    # Create a test location
    location = Location(
        name="Test Location",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    # Mock weather data
    mock_weather_data = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=datetime.now(timezone.utc),
        condition_text="Sunny",
        humidity=65,
        pressure=1013.25,
        wind_speed=10.5,
        wind_direction=180,
    )

    # Create collector and mock the NOAA client
    collector = WeatherCollector()
    collector.noaa_client.get_current_weather = AsyncMock(
        return_value=mock_weather_data
    )

    # Collect weather data
    await collector._collect_for_location(db_session, location)

    # Commit the transaction (normally done by collect_all)
    db_session.commit()

    # Verify data was stored
    weather_records = (
        db_session.query(WeatherData)
        .filter(WeatherData.location_id == location.id)
        .all()
    )
    assert len(weather_records) == 1
    assert weather_records[0].temperature == 20.0
    assert weather_records[0].source_api == "noaa"
    assert weather_records[0].condition_text == "Sunny"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_for_location_non_us(db_session):
    """Test that non-US locations use open-meteo client."""
    # Create a non-US location
    location = Location(
        name="London, UK",
        latitude=51.5074,
        longitude=-0.1278,
        country_code="GB",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    # Mock weather data
    mock_weather_data = APIWeatherData(
        temperature=8.3,
        temperature_fahrenheit=46.94,
        timestamp=datetime.now(timezone.utc),
        condition_text="Slight rain",
        humidity=78,
        pressure=1005.4,
        wind_speed=4.2,
        wind_direction=210,
    )

    collector = WeatherCollector()
    collector.open_meteo_client.get_current_weather = AsyncMock(
        return_value=mock_weather_data
    )

    # Collect weather data (should succeed via open-meteo)
    await collector._collect_for_location(db_session, location)

    # Commit the transaction
    db_session.commit()

    # Verify data was stored
    weather_records = (
        db_session.query(WeatherData)
        .filter(WeatherData.location_id == location.id)
        .all()
    )
    assert len(weather_records) == 1
    assert weather_records[0].temperature == 8.3
    assert weather_records[0].source_api == "open-meteo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_all_success(db_session):
    """Test collecting weather for all enabled locations."""
    # Create multiple enabled locations
    location1 = Location(
        name="Location 1",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    location2 = Location(
        name="Location 2",
        latitude=40.7128,
        longitude=-74.0060,
        country_code="US",
        enabled=True,
    )
    location3 = Location(
        name="Location 3 (disabled)",
        latitude=34.0522,
        longitude=-118.2437,
        country_code="US",
        enabled=False,  # Should be skipped
    )
    db_session.add_all([location1, location2, location3])
    db_session.commit()

    # Mock weather data
    mock_weather_data = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=datetime.now(timezone.utc),
        condition_text="Sunny",
    )

    # Patch SessionLocal to return our test db_session
    with patch("app.services.collectors.weather_collector.SessionLocal") as mock_sl:
        mock_sl.return_value = db_session

        # Create collector and mock the NOAA client
        collector = WeatherCollector()
        collector.noaa_client.get_current_weather = AsyncMock(
            return_value=mock_weather_data
        )

        # Collect all
        stats = await collector.collect_all()

        # Verify statistics
        assert stats["total_locations"] == 2  # Only enabled locations
        assert stats["success_count"] == 2
        assert stats["error_count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_all_with_errors(db_session, capsys):
    """Test collect_all handles errors gracefully."""
    # Create locations
    location1 = Location(
        name="Location 1",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    location2 = Location(
        name="Location 2",
        latitude=40.7128,
        longitude=-74.0060,
        country_code="US",
        enabled=True,
    )
    db_session.add_all([location1, location2])
    db_session.commit()

    # Mock weather data for first location, error for second
    mock_weather_data = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=datetime.now(timezone.utc),
        condition_text="Sunny",
    )

    # Patch SessionLocal
    with patch("app.services.collectors.weather_collector.SessionLocal") as mock_sl:
        mock_sl.return_value = db_session

        # Create collector
        collector = WeatherCollector()

        # First call succeeds, second fails
        collector.noaa_client.get_current_weather = AsyncMock(
            side_effect=[mock_weather_data, Exception("API Error")]
        )

        # Collect all
        stats = await collector.collect_all()

        # Verify statistics
        assert stats["total_locations"] == 2
        assert stats["success_count"] == 1
        assert stats["error_count"] == 1
        captured = capsys.readouterr()
        assert "Failed to collect weather" in captured.out


@pytest.mark.unit
def test_get_collector_singleton():
    """Test that get_collector returns the same instance."""
    collector1 = get_collector()
    collector2 = get_collector()
    assert collector1 is collector2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_all_sync_no_event_loop():
    """Test collect_all_sync when no event loop exists."""
    collector = WeatherCollector()

    # Mock the collect_all method
    expected_stats = {"success_count": 1, "error_count": 0, "total_locations": 1}

    with patch.object(collector, "collect_all", AsyncMock(return_value=expected_stats)):
        # This should use asyncio.run() in the except block
        stats = collector.collect_all_sync()
        assert stats == expected_stats


@pytest.mark.unit
@pytest.mark.asyncio
async def test_collect_for_location_preferred_api_override(db_session):
    """Test that preferred_api overrides country-based client selection."""
    # Create a US location with preferred_api="open-meteo"
    location = Location(
        name="San Francisco, CA",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        preferred_api="open-meteo",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    mock_weather_data = APIWeatherData(
        temperature=18.5,
        temperature_fahrenheit=65.3,
        timestamp=datetime.now(timezone.utc),
        condition_text="Partly cloudy",
        humidity=65,
    )

    collector = WeatherCollector()
    collector.open_meteo_client.get_current_weather = AsyncMock(
        return_value=mock_weather_data
    )

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    weather_records = (
        db_session.query(WeatherData)
        .filter(WeatherData.location_id == location.id)
        .all()
    )
    assert len(weather_records) == 1
    assert weather_records[0].source_api == "open-meteo"

    # Verify NOAA was NOT called (open-meteo was used instead)
    collector.open_meteo_client.get_current_weather.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_alert_upsert_inserts_new_alert(db_session):
    """Test that a new alert is inserted into the database."""
    location = Location(
        name="Test Location",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    now = datetime.now(timezone.utc)
    mock_weather = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=now,
        condition_text="Sunny",
    )
    mock_alert = WeatherAlert(
        alert_id="urn:oid:2.49.0.1.840.0.abc123",
        event="Tornado Warning",
        headline="Tornado Warning issued for Test County",
        description="A tornado has been sighted.",
        severity="Extreme",
        urgency="Immediate",
        effective=now,
        expires=now + timedelta(hours=1),
        areas=["Test County"],
    )

    collector = WeatherCollector()
    collector.noaa_client.get_current_weather = AsyncMock(return_value=mock_weather)
    collector.noaa_client.get_alerts = AsyncMock(return_value=[mock_alert])

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    alerts = db_session.query(Alert).filter(Alert.location_id == location.id).all()
    assert len(alerts) == 1
    assert alerts[0].alert_id == "urn:oid:2.49.0.1.840.0.abc123"
    assert alerts[0].event == "Tornado Warning"
    # SQLite strips tzinfo, so compare naive datetimes
    expected_expires = (now + timedelta(hours=1)).replace(tzinfo=None)
    assert alerts[0].expires.replace(tzinfo=None) == expected_expires


@pytest.mark.unit
@pytest.mark.asyncio
async def test_alert_upsert_updates_existing_alert(db_session):
    """Test that an existing alert is updated when NOAA returns it with changed fields."""
    location = Location(
        name="Test Location",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    now = datetime.now(timezone.utc)
    mock_weather = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=now,
        condition_text="Sunny",
    )

    # First collection: original alert
    original_alert = WeatherAlert(
        alert_id="urn:oid:2.49.0.1.840.0.abc123",
        event="Tornado Warning",
        headline="Tornado Warning issued for Test County",
        description="A tornado has been sighted.",
        severity="Extreme",
        urgency="Immediate",
        effective=now,
        expires=now + timedelta(hours=1),
        areas=["Test County"],
    )

    collector = WeatherCollector()
    collector.noaa_client.get_current_weather = AsyncMock(return_value=mock_weather)
    collector.noaa_client.get_alerts = AsyncMock(return_value=[original_alert])

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    # Second collection: same alert_id but extended expiry and updated description
    updated_alert = WeatherAlert(
        alert_id="urn:oid:2.49.0.1.840.0.abc123",  # Same ID
        event="Tornado Warning",
        headline="Tornado Warning EXTENDED for Test County",
        description="A tornado has been sighted. Warning extended.",
        severity="Extreme",
        urgency="Immediate",
        effective=now,
        expires=now + timedelta(hours=3),  # Extended from 1h to 3h
        areas=["Test County", "Nearby County"],  # Expanded area
    )

    collector.noaa_client.get_alerts = AsyncMock(return_value=[updated_alert])

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    # Should still be one alert row, not two
    alerts = db_session.query(Alert).filter(Alert.location_id == location.id).all()
    assert len(alerts) == 1

    # Fields should reflect the updated version
    alert = alerts[0]
    assert alert.headline == "Tornado Warning EXTENDED for Test County"
    assert alert.description == "A tornado has been sighted. Warning extended."
    expected_expires = (now + timedelta(hours=3)).replace(tzinfo=None)
    assert alert.expires.replace(tzinfo=None) == expected_expires
    assert "Nearby County" in alert.areas


@pytest.mark.unit
@pytest.mark.asyncio
async def test_alert_upsert_mixed_new_and_existing(db_session):
    """Test that a mix of new and existing alerts is handled correctly."""
    location = Location(
        name="Test Location",
        latitude=37.7749,
        longitude=-122.4194,
        country_code="US",
        enabled=True,
    )
    db_session.add(location)
    db_session.commit()
    db_session.refresh(location)

    now = datetime.now(timezone.utc)
    mock_weather = APIWeatherData(
        temperature=20.0,
        temperature_fahrenheit=68.0,
        timestamp=now,
        condition_text="Sunny",
    )

    # First collection: one alert
    alert1 = WeatherAlert(
        alert_id="alert-1",
        event="Flood Watch",
        headline="Flood Watch for Test County",
        description="Flooding possible.",
        severity="Moderate",
        urgency="Expected",
        effective=now,
        expires=now + timedelta(hours=6),
        areas=["Test County"],
    )

    collector = WeatherCollector()
    collector.noaa_client.get_current_weather = AsyncMock(return_value=mock_weather)
    collector.noaa_client.get_alerts = AsyncMock(return_value=[alert1])

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    # Second collection: first alert updated + a brand new alert
    alert1_updated = WeatherAlert(
        alert_id="alert-1",
        event="Flood Warning",  # Upgraded from Watch to Warning
        headline="Flood Warning for Test County",
        description="Flooding imminent.",
        severity="Severe",  # Upgraded
        urgency="Immediate",  # Upgraded
        effective=now,
        expires=now + timedelta(hours=6),
        areas=["Test County"],
    )
    alert2 = WeatherAlert(
        alert_id="alert-2",
        event="Wind Advisory",
        headline="Wind Advisory for Test County",
        description="High winds expected.",
        severity="Minor",
        urgency="Expected",
        effective=now,
        expires=now + timedelta(hours=12),
        areas=["Test County"],
    )

    collector.noaa_client.get_alerts = AsyncMock(
        return_value=[alert1_updated, alert2]
    )

    await collector._collect_for_location(db_session, location)
    db_session.commit()

    alerts = (
        db_session.query(Alert)
        .filter(Alert.location_id == location.id)
        .order_by(Alert.alert_id)
        .all()
    )
    assert len(alerts) == 2

    # alert-1 should be updated (Watch -> Warning)
    assert alerts[0].alert_id == "alert-1"
    assert alerts[0].event == "Flood Warning"
    assert alerts[0].severity == "Severe"

    # alert-2 should be newly inserted
    assert alerts[1].alert_id == "alert-2"
    assert alerts[1].event == "Wind Advisory"
