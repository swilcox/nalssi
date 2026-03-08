"""
Pydantic schemas for output backend configuration API endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BackendConfigCreate(BaseModel):
    """Schema for creating a new output backend configuration."""

    name: str = Field(..., min_length=1, max_length=255, description="Backend name")
    backend_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Backend type (redis, influxdb, etc.)",
    )
    enabled: bool = Field(True, description="Whether backend is enabled")
    connection_config: dict[str, Any] = Field(
        ..., description="Connection configuration (e.g., url, host, port)"
    )
    format_type: str | None = Field(
        None, max_length=50, description="Format type (kurokku, generic, etc.)"
    )
    format_config: dict[str, Any] | None = Field(
        None, description="Format-specific configuration"
    )
    location_filter: dict[str, Any] | None = Field(
        None, description="Location filter (null=all, {include:[...]}, {exclude:[...]})"
    )
    write_timeout: int = Field(10, gt=0, description="Write timeout in seconds")
    retry_count: int = Field(1, ge=0, description="Number of retries on failure")


class BackendConfigUpdate(BaseModel):
    """Schema for updating a backend configuration (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    backend_type: str | None = Field(None, min_length=1, max_length=50)
    enabled: bool | None = None
    connection_config: dict[str, Any] | None = None
    format_type: str | None = Field(None, max_length=50)
    format_config: dict[str, Any] | None = None
    location_filter: dict[str, Any] | None = None
    write_timeout: int | None = Field(None, gt=0)
    retry_count: int | None = Field(None, ge=0)


class BackendConfigResponse(BaseModel):
    """Schema for backend configuration response."""

    id: UUID
    name: str
    backend_type: str
    enabled: bool
    connection_config: dict[str, Any]
    format_type: str | None
    format_config: dict[str, Any] | None
    location_filter: dict[str, Any] | None
    write_timeout: int
    retry_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
