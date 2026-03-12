"""
Base class for weather API clients.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WeatherData:
    """Normalized weather data structure."""

    temperature: float  # Celsius
    temperature_fahrenheit: float
    timestamp: datetime
    condition_text: str
    humidity: int | None = None
    pressure: float | None = None  # hPa
    wind_speed: float | None = None  # m/s
    wind_direction: int | None = None  # degrees
    wind_gust: float | None = None  # m/s
    feels_like: float | None = None  # Celsius
    visibility: int | None = None  # meters
    cloud_cover: int | None = None  # percentage
    precipitation: float | None = None  # mm
    uv_index: int | None = None
    condition_code: str | None = None
    icon: str | None = None
    raw_data: dict | None = None


@dataclass
class WeatherAlert:
    """Normalized weather alert structure."""

    event: str
    headline: str
    description: str
    severity: str  # Extreme, Severe, Moderate, Minor, Unknown
    urgency: str  # Immediate, Expected, Future, Past, Unknown
    effective: datetime
    expires: datetime
    areas: list[str]
    instruction: str | None = None
    alert_id: str | None = None
    certainty: str | None = None  # Observed, Likely, Possible, Unlikely, Unknown
    category: str | None = None  # Met, Fire, Geo, Health, Env, Transport, etc.
    response_type: str | None = None  # Shelter, Evacuate, Prepare, Monitor, etc.
    sender_name: str | None = None  # Issuing NWS office
    status: str | None = None  # Actual, Exercise, System, Test, Draft
    message_type: str | None = None  # Alert, Update, Cancel
    onset: datetime | None = None  # Expected onset of the event
    ends: datetime | None = None  # Expected end of the event


class BaseWeatherClient(ABC):
    """Abstract base class for weather API clients."""

    def __init__(self, base_url: str, name: str):
        """
        Initialize the weather client.

        Args:
            base_url: Base URL for the weather API
            name: Identifier name for this client (e.g., 'noaa', 'open-meteo')
        """
        self.base_url = base_url
        self.name = name

    @abstractmethod
    async def get_current_weather(
        self, latitude: float, longitude: float
    ) -> WeatherData:
        """
        Get current weather for a location.

        Args:
            latitude: Latitude coordinate (-90 to 90)
            longitude: Longitude coordinate (-180 to 180)

        Returns:
            WeatherData object with normalized weather information

        Raises:
            ValueError: If coordinates are invalid
            Exception: If API request fails
        """
        pass

    @abstractmethod
    async def get_alerts(self, latitude: float, longitude: float) -> list[WeatherAlert]:
        """
        Get active weather alerts for a location.

        Args:
            latitude: Latitude coordinate (-90 to 90)
            longitude: Longitude coordinate (-180 to 180)

        Returns:
            List of WeatherAlert objects

        Raises:
            ValueError: If coordinates are invalid
            Exception: If API request fails
        """
        pass

    def validate_coordinates(self, latitude: float, longitude: float) -> None:
        """
        Validate latitude and longitude coordinates.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Raises:
            ValueError: If coordinates are out of valid range
        """
        if not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180")

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name='{self.name}' base_url='{self.base_url}'>"
        )
