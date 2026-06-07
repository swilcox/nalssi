"""
Output backend configuration model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OutputBackendConfig(Base):
    """
    Configuration for an output backend (e.g., Redis, InfluxDB, Prometheus).
    """

    __tablename__ = "output_backend_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    backend_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # redis, influxdb, etc.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Connection settings (JSON string)
    connection_config: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # {"url": "redis://...", ...}

    # Format settings
    format_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # kurokku, generic, etc.
    format_config: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON format-specific config

    # Location filtering (JSON string, null = all locations)
    location_filter: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # {"include": [...]} or {"exclude": [...]}

    # Write behavior
    write_timeout: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )  # seconds
    retry_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

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

    def __repr__(self):
        return f"<OutputBackendConfig(id={self.id}, name='{self.name}', type='{self.backend_type}')>"

    def __str__(self):
        return f"Backend: {self.name} ({self.backend_type})"
