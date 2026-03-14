"""
Forecast model for storing weather forecast periods.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Forecast(Base):
    """
    Represents a single forecast period for a location.

    Each row is one time block (e.g. a 12-hour NOAA period, a 3-hour
    OpenWeather block, or an hourly Open-Meteo entry).
    """

    __tablename__ = "forecasts"

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
    source_api = Column(String(50), nullable=False)

    # Time range for this forecast period
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Conditions
    temperature = Column(Float, nullable=True)  # Celsius (high for day, low for night)
    temperature_fahrenheit = Column(Float, nullable=True)
    temp_low = Column(Float, nullable=True)  # Celsius (for daily periods)
    temp_low_fahrenheit = Column(Float, nullable=True)
    feels_like = Column(Float, nullable=True)  # Celsius
    humidity = Column(Integer, nullable=True)  # percentage
    pressure = Column(Float, nullable=True)  # hPa
    wind_speed = Column(Float, nullable=True)  # m/s
    wind_direction = Column(Integer, nullable=True)  # degrees
    wind_gust = Column(Float, nullable=True)  # m/s
    precipitation_probability = Column(Integer, nullable=True)  # percentage
    precipitation_amount = Column(Float, nullable=True)  # mm
    cloud_cover = Column(Integer, nullable=True)  # percentage
    visibility = Column(Integer, nullable=True)  # meters
    uv_index = Column(Float, nullable=True)

    # Descriptions
    condition_text = Column(String(255), nullable=True)  # e.g. "Partly Cloudy"
    condition_code = Column(String(50), nullable=True)
    is_daytime = Column(Boolean, nullable=True)
    detailed_forecast = Column(Text, nullable=True)  # NOAA narrative paragraph

    # Metadata
    fetched_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location = relationship("Location", back_populates="forecasts")

    __table_args__ = (
        # Find forecast periods for a location within a time range
        Index("ix_forecasts_location_time", "location_id", "start_time"),
        # Dedup: one period per location+source+start_time
        Index(
            "ix_forecasts_dedup",
            "location_id",
            "source_api",
            "start_time",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<Forecast(id={self.id}, location_id={self.location_id}, "
            f"start={self.start_time}, temp={self.temperature})>"
        )
