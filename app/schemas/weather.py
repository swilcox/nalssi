"""
Pydantic schemas for Weather API endpoints.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CurrentWeatherResponse(BaseModel):
    """Schema for current weather response."""

    location_id: UUID
    location_name: str
    temperature: float
    temperature_fahrenheit: float
    condition_text: str
    humidity: int | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_direction: int | None = None
    wind_gust: float | None = None
    visibility: int | None = None
    timestamp: datetime
    source_api: str
    raw_data: dict | None = None

    model_config = {"from_attributes": True}


class WeatherAlertResponse(BaseModel):
    """Schema for weather alert response."""

    event: str
    headline: str
    severity: str
    urgency: str
    certainty: str | None = None
    category: str | None = None
    response_type: str | None = None
    sender_name: str | None = None
    status: str | None = None
    message_type: str | None = None
    effective: datetime
    expires: datetime
    onset: datetime | None = None
    ends: datetime | None = None
    areas: list[str]
    description: str | None = None
    instruction: str | None = None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str
    version: str
    timestamp: str
