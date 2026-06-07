"""
Forecast model for storing weather forecast periods.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.location import Location


class Forecast(Base):
    """
    Represents a single forecast period for a location.

    Each row is one time block (e.g. a 12-hour NOAA period, a 3-hour
    OpenWeather block, or an hourly Open-Meteo entry).
    """

    __tablename__ = "forecasts"

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
    source_api: Mapped[str] = mapped_column(String(50), nullable=False)

    # Time range for this forecast period
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Conditions
    temperature: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Celsius (high for day, low for night)
    temperature_fahrenheit: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_low: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Celsius (for daily periods)
    temp_low_fahrenheit: Mapped[float | None] = mapped_column(Float, nullable=True)
    feels_like: Mapped[float | None] = mapped_column(Float, nullable=True)  # Celsius
    humidity: Mapped[int | None] = mapped_column(Integer, nullable=True)  # percentage
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)  # hPa
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    wind_direction: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # degrees
    wind_gust: Mapped[float | None] = mapped_column(Float, nullable=True)  # m/s
    precipitation_probability: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # percentage
    precipitation_amount: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # mm
    cloud_cover: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # percentage
    visibility: Mapped[int | None] = mapped_column(Integer, nullable=True)  # meters
    uv_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Descriptions
    condition_text: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # e.g. "Partly Cloudy"
    condition_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_daytime: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    detailed_forecast: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # NOAA narrative paragraph

    # Metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location: Mapped[Location] = relationship("Location", back_populates="forecasts")

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
