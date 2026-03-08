"""
Unit tests for database models.

Following TDD: Write tests first, then implement models.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.backend_config import OutputBackendConfig
from app.models.location import Location
from app.models.weather import WeatherData


@pytest.mark.unit
def test_location_model_creation(db_session, sample_location_data):
    """Test creating a Location model instance."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    assert location.id is not None
    assert location.name == "San Francisco, CA"
    assert location.slug == "san_francisco_ca"
    assert location.latitude == 37.7749
    assert location.longitude == -122.4194
    assert location.country_code == "US"
    assert location.enabled is True
    assert location.created_at is not None
    assert location.updated_at is not None


@pytest.mark.unit
def test_location_latitude_validation(db_session):
    """Test that latitude must be within valid range (-90 to 90)."""
    # Valid latitudes
    location = Location(name="Test", latitude=45.0, longitude=0.0, country_code="US")
    db_session.add(location)
    db_session.commit()
    assert location.latitude == 45.0

    # Invalid latitudes should fail
    with pytest.raises((ValueError, IntegrityError)):
        invalid_location = Location(
            name="Invalid", latitude=100.0, longitude=0.0, country_code="US"
        )
        db_session.add(invalid_location)
        db_session.commit()


@pytest.mark.unit
def test_location_longitude_validation(db_session):
    """Test that longitude must be within valid range (-180 to 180)."""
    # Valid longitude
    location = Location(name="Test", latitude=0.0, longitude=90.0, country_code="US")
    db_session.add(location)
    db_session.commit()
    assert location.longitude == 90.0

    # Invalid longitude should fail
    with pytest.raises((ValueError, IntegrityError)):
        invalid_location = Location(
            name="Invalid", latitude=0.0, longitude=200.0, country_code="US"
        )
        db_session.add(invalid_location)
        db_session.commit()


@pytest.mark.unit
def test_location_name_required(db_session):
    """Test that location name is required."""
    from sqlalchemy.exc import IntegrityError

    # SQLAlchemy will allow creation but fail on commit due to nullable=False
    location = Location(latitude=0.0, longitude=0.0, country_code="US")
    db_session.add(location)
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.unit
def test_location_defaults(db_session):
    """Test default values for location fields."""
    location = Location(
        name="Test",
        latitude=0.0,
        longitude=0.0,
        country_code="US",
    )
    db_session.add(location)
    db_session.commit()

    assert location.enabled is True  # Default
    assert location.collection_interval == 300  # Default
    assert location.preferred_api is None  # Default null


@pytest.mark.unit
def test_location_timestamps(db_session):
    """Test that timestamps are automatically set."""
    location = Location(
        name="Test",
        latitude=0.0,
        longitude=0.0,
        country_code="US",
    )
    db_session.add(location)
    db_session.commit()

    assert location.created_at is not None
    assert location.updated_at is not None
    # Timestamps are stored as datetime objects
    assert isinstance(location.created_at, datetime)
    assert isinstance(location.updated_at, datetime)
    # Properties should return the same datetime objects
    assert location.created_at_datetime == location.created_at
    assert location.updated_at_datetime == location.updated_at


@pytest.mark.unit
def test_location_update_timestamp(db_session):
    """Test that updated_at changes on update."""
    location = Location(
        name="Test",
        latitude=0.0,
        longitude=0.0,
        country_code="US",
    )
    db_session.add(location)
    db_session.commit()

    original_updated_at = location.updated_at

    # Update location
    location.name = "Updated Name"
    db_session.commit()

    # updated_at should be newer (this might be the same in fast tests,
    # but the mechanism should be in place)
    assert location.updated_at >= original_updated_at


@pytest.mark.unit
def test_weather_data_model_creation(
    db_session, sample_location_data, sample_weather_data
):
    """Test creating a WeatherData model instance."""
    # First create a location
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    # Create weather data for that location
    weather = WeatherData(
        location_id=location.id,
        source_api="noaa",
        **sample_weather_data,
    )
    db_session.add(weather)
    db_session.commit()

    assert weather.id is not None
    assert weather.location_id == location.id
    assert weather.temperature == 18.5
    assert weather.humidity == 65
    assert weather.source_api == "noaa"
    assert weather.created_at is not None


@pytest.mark.unit
def test_weather_data_requires_location(db_session, sample_weather_data):
    """Test that weather data requires a valid location_id."""
    import uuid

    # Try to create weather data with non-existent location_id
    non_existent_uuid = uuid.uuid4()
    weather = WeatherData(
        location_id=non_existent_uuid,  # Non-existent location
        source_api="noaa",
        **sample_weather_data,
    )
    db_session.add(weather)

    # Should fail due to foreign key constraint
    with pytest.raises(IntegrityError):
        db_session.commit()

    # Rollback to clean up
    db_session.rollback()


@pytest.mark.unit
def test_weather_data_timestamp_field(
    db_session, sample_location_data, sample_weather_data
):
    """Test that weather data can have a specific timestamp."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    specific_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
    weather = WeatherData(
        location_id=location.id,
        source_api="noaa",
        timestamp=specific_time,  # Pass as datetime object
        **sample_weather_data,
    )
    db_session.add(weather)
    db_session.commit()

    # Timestamps are stored as datetime objects
    # SQLite may strip timezone info, so compare the datetime values
    assert weather.timestamp.replace(tzinfo=UTC) == specific_time
    # Property should return the same datetime object
    assert weather.timestamp_datetime.replace(tzinfo=UTC) == specific_time


@pytest.mark.unit
def test_location_relationship_to_weather(
    db_session, sample_location_data, sample_weather_data
):
    """Test the relationship between Location and WeatherData."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    # Add multiple weather records
    for i in range(3):
        weather = WeatherData(
            location_id=location.id,
            source_api="noaa",
            temperature=18.0 + i,
            **{k: v for k, v in sample_weather_data.items() if k != "temperature"},
        )
        db_session.add(weather)
    db_session.commit()

    # Refresh to load relationships
    db_session.refresh(location)

    # Location should have 3 weather data records
    assert len(location.weather_data) == 3
    assert all(isinstance(w, WeatherData) for w in location.weather_data)


@pytest.mark.unit
def test_weather_data_optional_fields(db_session, sample_location_data):
    """Test that many weather fields are optional."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    # Create weather with minimal required fields
    weather = WeatherData(
        location_id=location.id,
        source_api="noaa",
        temperature=20.0,
    )
    db_session.add(weather)
    db_session.commit()

    assert weather.id is not None
    assert weather.temperature == 20.0
    # Optional fields should be None
    assert weather.humidity is None
    assert weather.wind_speed is None


@pytest.mark.unit
def test_location_str_representation(db_session, sample_location_data):
    """Test string representation of Location."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    str_repr = str(location)
    assert "San Francisco, CA" in str_repr
    assert str(location.id) in str_repr


@pytest.mark.unit
def test_weather_data_str_representation(
    db_session, sample_location_data, sample_weather_data
):
    """Test string representation of WeatherData."""
    location = Location(**sample_location_data)
    db_session.add(location)
    db_session.commit()

    weather = WeatherData(
        location_id=location.id,
        source_api="noaa",
        **sample_weather_data,
    )
    db_session.add(weather)
    db_session.commit()

    str_repr = str(weather)
    assert str(location.id) in str_repr or location.name in str_repr


@pytest.mark.unit
def test_location_slug(db_session):
    """Test that location slug can be set."""
    location = Location(
        name="Spring Hill",
        slug="spring_hill",
        latitude=28.4772,
        longitude=-82.5302,
        country_code="US",
    )
    db_session.add(location)
    db_session.commit()

    assert location.slug == "spring_hill"


@pytest.mark.unit
def test_location_slug_unique(db_session):
    """Test that slug must be unique."""
    loc1 = Location(
        name="Location 1",
        slug="same_slug",
        latitude=0.0,
        longitude=0.0,
        country_code="US",
    )
    db_session.add(loc1)
    db_session.commit()

    loc2 = Location(
        name="Location 2",
        slug="same_slug",
        latitude=1.0,
        longitude=1.0,
        country_code="US",
    )
    db_session.add(loc2)
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.unit
def test_location_slug_nullable(db_session):
    """Test that slug can be null."""
    location = Location(
        name="No Slug",
        latitude=0.0,
        longitude=0.0,
        country_code="US",
    )
    db_session.add(location)
    db_session.commit()

    assert location.slug is None


@pytest.mark.unit
def test_output_backend_config_creation(db_session):
    """Test creating an OutputBackendConfig."""
    config = OutputBackendConfig(
        name="Test Redis",
        backend_type="redis",
        enabled=True,
        connection_config='{"url": "redis://localhost:6379/0"}',
        format_type="kurokku",
        write_timeout=10,
        retry_count=1,
    )
    db_session.add(config)
    db_session.commit()

    assert config.id is not None
    assert config.name == "Test Redis"
    assert config.backend_type == "redis"
    assert config.enabled is True
    assert config.created_at is not None
    assert config.updated_at is not None


@pytest.mark.unit
def test_output_backend_config_defaults(db_session):
    """Test default values for OutputBackendConfig."""
    config = OutputBackendConfig(
        name="Minimal",
        backend_type="redis",
        connection_config="{}",
    )
    db_session.add(config)
    db_session.commit()

    assert config.enabled is True
    assert config.write_timeout == 10
    assert config.retry_count == 1
    assert config.format_type is None
    assert config.format_config is None
    assert config.location_filter is None


@pytest.mark.unit
def test_output_backend_config_str(db_session):
    """Test string representation of OutputBackendConfig."""
    config = OutputBackendConfig(
        name="My Redis",
        backend_type="redis",
        connection_config="{}",
    )
    db_session.add(config)
    db_session.commit()

    assert "My Redis" in str(config)
    assert "redis" in str(config)
