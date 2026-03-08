"""
Pydantic schemas for Location API endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LocationBase(BaseModel):
    """Base schema for Location."""

    name: str = Field(..., min_length=1, max_length=255, description="Location name")
    slug: str | None = Field(
        None,
        max_length=100,
        description="URL/key-friendly slug (auto-generated from name if not provided)",
    )
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (-90 to 90)")
    longitude: float = Field(
        ..., ge=-180, le=180, description="Longitude (-180 to 180)"
    )
    timezone: str | None = Field(None, max_length=100, description="Timezone")
    country_code: str = Field(
        ..., min_length=2, max_length=2, description="ISO country code"
    )
    enabled: bool = Field(
        True, description="Whether location is enabled for collection"
    )
    collection_interval: int = Field(
        300, gt=0, description="Collection interval in seconds"
    )
    preferred_api: str | None = Field(
        None,
        max_length=50,
        description="Preferred weather API (noaa, open-meteo, etc.)",
    )


class LocationCreate(LocationBase):
    """Schema for creating a new location."""

    pass


class LocationUpdate(BaseModel):
    """Schema for updating a location (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=100)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    timezone: str | None = Field(None, max_length=100)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    enabled: bool | None = None
    collection_interval: int | None = Field(None, gt=0)
    preferred_api: str | None = Field(None, max_length=50)


class LocationResponse(LocationBase):
    """Schema for location response."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
