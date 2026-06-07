"""
Weather Alert model for storing weather alerts and warnings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# CAP standard values for reference:
# category: Met, Fire, Geo, Health, Env, Transport, Infra, CBRNE, Other
# response_type: Shelter, Evacuate, Prepare, Execute, Avoid, Monitor, AllClear, None
# status: Actual, Exercise, System, Test, Draft
# message_type: Alert, Update, Cancel, Ack, Error
from app.database import Base

if TYPE_CHECKING:
    from app.models.location import Location


class Alert(Base):
    """
    Represents a weather alert/warning for a location.

    Stores alerts from various sources (NOAA, etc.) with deduplication
    to avoid storing the same alert multiple times.
    """

    __tablename__ = "alerts"

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

    # Alert identification - used for deduplication
    alert_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="External alert ID from source API for deduplication",
    )
    source_api: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # noaa, open-meteo, etc.

    # Alert metadata
    event: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )  # e.g., "High Wind Warning"
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Extreme, Severe, Moderate, Minor, Unknown
    urgency: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # Immediate, Expected, Future, Past, Unknown
    certainty: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Observed, Likely, Possible, Unlikely, Unknown

    # CAP classification fields
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Met, Fire, Geo, Health, Env, Transport, etc.
    response_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # Shelter, Evacuate, Prepare, Monitor, etc.
    sender_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Issuing office (e.g., "NWS Tulsa OK")
    status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Actual, Exercise, System, Test, Draft
    message_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # Alert, Update, Cancel

    # Time information
    effective: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )  # When alert becomes effective
    expires: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )  # When alert expires
    onset: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Expected onset of event
    ends: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Expected end of event

    # Geographic areas affected (JSON array stored as string)
    areas: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON array of area names

    # Alert content
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        comment="When this alert was fetched and stored",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location: Mapped[Location] = relationship("Location", back_populates="alerts")

    # Indexes for common queries
    __table_args__ = (
        # Composite index for finding active alerts
        Index("ix_alerts_location_expires", "location_id", "expires"),
        # Unique constraint for deduplication (same alert_id from same source for same location)
        Index("ix_alerts_dedup", "location_id", "alert_id", "source_api", unique=True),
    )

    def __repr__(self):
        return f"<Alert(id={self.id}, event={self.event}, severity={self.severity})>"

    def __str__(self):
        location_info = f"Location ID: {self.location_id}"
        if self.location:
            location_info = f"Location: {self.location.name}"
        return f"Alert: {self.event} ({self.severity}) at {location_info}"

    @property
    def effective_datetime(self):
        """Get effective as datetime object (for backwards compatibility)."""
        return self.effective

    @property
    def expires_datetime(self):
        """Get expires as datetime object (for backwards compatibility)."""
        return self.expires

    @property
    def is_active(self):
        """Check if alert is currently active (not expired)."""
        now = datetime.now(UTC)
        return self.expires > now

    @property
    def is_future(self):
        """Check if alert is for a future event (not yet effective)."""
        now = datetime.now(UTC)
        return self.effective > now
