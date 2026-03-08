"""
WeatherData model for storing weather observations.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class WeatherData(Base):
    """
    Represents a weather data observation for a location.
    Stores normalized weather data from various API sources.
    """

    __tablename__ = "weather_data"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    location_id = Column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    source_api = Column(String(50), nullable=False)  # noaa, open-meteo, etc.

    # Current conditions
    temperature = Column(Float, nullable=True)  # Celsius
    temperature_fahrenheit = Column(Float, nullable=True)
    feels_like = Column(Float, nullable=True)  # Celsius
    humidity = Column(Integer, nullable=True)  # percentage
    pressure = Column(Float, nullable=True)  # hPa
    wind_speed = Column(Float, nullable=True)  # m/s
    wind_direction = Column(Integer, nullable=True)  # degrees
    wind_gust = Column(Float, nullable=True)  # m/s
    precipitation = Column(Float, nullable=True)  # mm
    cloud_cover = Column(Integer, nullable=True)  # percentage
    visibility = Column(Integer, nullable=True)  # meters
    uv_index = Column(Integer, nullable=True)

    # Conditions
    condition_code = Column(String(50), nullable=True)
    condition_text = Column(String(255), nullable=True)
    icon = Column(String(50), nullable=True)

    # Additional data
    sunrise = Column(DateTime(timezone=True), nullable=True)
    sunset = Column(DateTime(timezone=True), nullable=True)
    raw_data = Column(Text, nullable=True)  # JSON string of original API response

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location = relationship("Location", back_populates="weather_data")

    def __repr__(self):
        return f"<WeatherData(id={self.id}, location_id={self.location_id}, temp={self.temperature})>"

    def __str__(self):
        location_info = f"Location ID: {self.location_id}"
        if self.location:
            location_info = f"Location: {self.location.name}"
        return f"WeatherData: {self.temperature}°C at {location_info}"

    @property
    def timestamp_datetime(self):
        """Get timestamp as datetime object (for backwards compatibility)."""
        return self.timestamp

    @property
    def created_at_datetime(self):
        """Get created_at as datetime object (for backwards compatibility)."""
        return self.created_at
