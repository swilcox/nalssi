"""
Radar frame model for storing per-location radar imagery history.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.location import Location


class RadarFrame(Base):
    """
    Represents one stored radar image for a location at a point in time.

    Only metadata lives here; the PNG itself is written under
    ``settings.RADAR_STORAGE_DIR`` and referenced by ``file_path``. Keeping the
    bytes out of the database avoids bloating it with binary data that is
    pruned on a rolling two hour window anyway.
    """

    __tablename__ = "radar_frames"

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

    # Timestamp of the radar observation itself, as advertised by the WMS
    # time dimension (not when we downloaded it).
    frame_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Path to the PNG, relative to settings.RADAR_STORAGE_DIR.
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    location: Mapped[Location] = relationship("Location", back_populates="radar_frames")

    __table_args__ = (
        # Playback order and retention pruning both scan by location + time
        Index("ix_radar_frames_location_time", "location_id", "frame_time"),
        # Dedup: one stored image per location+frame timestamp
        Index(
            "ix_radar_frames_dedup",
            "location_id",
            "frame_time",
            unique=True,
        ),
    )

    @property
    def frame_time_utc(self) -> datetime:
        """
        Get frame_time as a timezone-aware UTC datetime.

        SQLite has no native timezone support, so values read back from it are
        naive even though the column is declared timezone-aware. Frames are
        always stored as UTC, so attaching UTC is the correct normalization.
        """
        if self.frame_time.tzinfo is None:
            return self.frame_time.replace(tzinfo=UTC)
        return self.frame_time.astimezone(UTC)

    @property
    def epoch(self) -> int:
        """
        Get the epoch-second identifier used in this frame's filename and URL.

        Derived from the UTC-normalized timestamp so it round-trips correctly
        regardless of the server's local timezone.
        """
        return int(self.frame_time_utc.timestamp())

    def __repr__(self):
        return (
            f"<RadarFrame(id={self.id}, location_id={self.location_id}, "
            f"frame_time={self.frame_time})>"
        )
