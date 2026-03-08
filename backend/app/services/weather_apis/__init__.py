"""
Weather API clients for different providers.
"""

from app.services.weather_apis.base import (
    BaseWeatherClient,
    WeatherAlert,
    WeatherData,
)
from app.services.weather_apis.noaa import NOAAWeatherClient
from app.services.weather_apis.open_meteo import OpenMeteoClient
from app.services.weather_apis.openweather import OpenWeatherClient

__all__ = [
    "BaseWeatherClient",
    "WeatherData",
    "WeatherAlert",
    "NOAAWeatherClient",
    "OpenMeteoClient",
    "OpenWeatherClient",
]
