"""
Location model for storing geographic locations to monitor.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.forecast import Forecast
    from app.models.weather import WeatherData


class Location(Base):
    """
    Represents a geographic location to collect weather data for.
    """

    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    collection_interval: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )  # seconds
    preferred_api: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # noaa, open-meteo, etc.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="check_latitude"),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180", name="check_longitude"
        ),
        CheckConstraint("collection_interval > 0", name="check_collection_interval"),
    )

    # Relationships
    weather_data: Mapped[list[WeatherData]] = relationship(
        "WeatherData", back_populates="location", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        "Alert", back_populates="location", cascade="all, delete-orphan"
    )
    forecasts: Mapped[list[Forecast]] = relationship(
        "Forecast", back_populates="location", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Location(id={self.id}, name='{self.name}')>"

    def __str__(self):
        return f"Location: {self.name} (ID: {self.id})"

    @property
    def created_at_datetime(self):
        """Get created_at as datetime object (for backwards compatibility)."""
        return self.created_at

    @property
    def updated_at_datetime(self):
        """Get updated_at as datetime object (for backwards compatibility)."""
        return self.updated_at
