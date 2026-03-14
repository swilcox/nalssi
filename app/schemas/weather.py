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


class ForecastPeriodResponse(BaseModel):
    """Schema for a single forecast period."""

    start_time: datetime
    end_time: datetime
    temperature: float | None = None
    temperature_fahrenheit: float | None = None
    temp_low: float | None = None
    temp_low_fahrenheit: float | None = None
    feels_like: float | None = None
    humidity: int | None = None
    pressure: float | None = None
    wind_speed: float | None = None
    wind_direction: int | None = None
    wind_gust: float | None = None
    precipitation_probability: int | None = None
    precipitation_amount: float | None = None
    cloud_cover: int | None = None
    visibility: int | None = None
    uv_index: float | None = None
    condition_text: str | None = None
    condition_code: str | None = None
    is_daytime: bool | None = None
    detailed_forecast: str | None = None

    model_config = {"from_attributes": True}


class ForecastResponse(BaseModel):
    """Schema for forecast response for a location."""

    location_id: UUID
    location_name: str
    source_api: str
    periods: list[ForecastPeriodResponse]

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """Schema for health check response."""

    status: str
    version: str
    timestamp: str
