"""
WeatherData model for storing weather observations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.location import Location


class WeatherData(Base):
    """
    Represents a weather data observation for a location.
    Stores normalized weather data from various API sources.
    """

    __tablename__ = "weather_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    source_api: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # noaa, open-meteo, etc.

    # Current conditions
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)  # Celsius
    temperature_fahrenheit: Mapped[float | None] = mapped_column(Float, nullable=True)
    feels_like: Mapped[float | None] = mapped_column(Float, nullable=True)  # Celsius
    humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # percentage
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)  # hPa
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    wind_direction: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # degrees
    wind_gust: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    precipitation: Mapped[float | None] = mapped_column(Float, nullable=True)  # mm
    cloud_cover: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # percentage
    visibility: Mapped[int | None] = mapped_column(Integer, nullable=True)  # meters
    uv_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Conditions
    condition_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    condition_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Additional data
    sunrise: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sunset: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_data: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string of original API response

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location: Mapped[Location] = relationship("Location", back_populates="weather_data")

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
