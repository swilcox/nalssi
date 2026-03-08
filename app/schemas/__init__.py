"""
Pydantic schemas for API request/response models.
"""

from app.schemas.backend_config import (
    BackendConfigCreate,
    BackendConfigResponse,
    BackendConfigUpdate,
)
from app.schemas.location import LocationCreate, LocationResponse, LocationUpdate
from app.schemas.weather import (
    CurrentWeatherResponse,
    HealthResponse,
    WeatherAlertResponse,
)

__all__ = [
    "LocationCreate",
    "LocationUpdate",
    "LocationResponse",
    "CurrentWeatherResponse",
    "WeatherAlertResponse",
    "HealthResponse",
    "BackendConfigCreate",
    "BackendConfigUpdate",
    "BackendConfigResponse",
]
