"""
Database models for the nalssi application.
"""

from app.models.alert import Alert
from app.models.backend_config import OutputBackendConfig
from app.models.forecast import Forecast
from app.models.location import Location
from app.models.weather import WeatherData

__all__ = ["Location", "WeatherData", "Alert", "Forecast", "OutputBackendConfig"]
