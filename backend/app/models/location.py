"""
Location model for storing geographic locations to monitor.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Location(Base):
    """
    Represents a geographic location to collect weather data for.
    """

    __tablename__ = "locations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), nullable=True, unique=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timezone = Column(String(100), nullable=True)
    country_code = Column(String(2), nullable=False, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    collection_interval = Column(Integer, default=300, nullable=False)  # seconds
    preferred_api = Column(String(50), nullable=True)  # noaa, open-meteo, etc.

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
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
    weather_data = relationship(
        "WeatherData", back_populates="location", cascade="all, delete-orphan"
    )
    alerts = relationship(
        "Alert", back_populates="location", cascade="all, delete-orphan"
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
