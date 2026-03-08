"""
Output backend configuration model.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class OutputBackendConfig(Base):
    """
    Configuration for an output backend (e.g., Redis, InfluxDB, Prometheus).
    """

    __tablename__ = "output_backend_configs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    backend_type = Column(
        String(50), nullable=False, index=True
    )  # redis, influxdb, etc.
    enabled = Column(Boolean, default=True, nullable=False)

    # Connection settings (JSON string)
    connection_config = Column(Text, nullable=False)  # {"url": "redis://...", ...}

    # Format settings
    format_type = Column(String(50), nullable=True)  # kurokku, generic, etc.
    format_config = Column(Text, nullable=True)  # JSON format-specific config

    # Location filtering (JSON string, null = all locations)
    location_filter = Column(
        Text, nullable=True
    )  # {"include": [...]} or {"exclude": [...]}

    # Write behavior
    write_timeout = Column(Integer, default=10, nullable=False)  # seconds
    retry_count = Column(Integer, default=1, nullable=False)

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

    def __repr__(self):
        return f"<OutputBackendConfig(id={self.id}, name='{self.name}', type='{self.backend_type}')>"

    def __str__(self):
        return f"Backend: {self.name} ({self.backend_type})"
