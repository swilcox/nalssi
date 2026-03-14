"""
Open-Meteo API client.

Documentation: https://open-meteo.com/
Free for non-commercial use. No API key required. Global coverage.
"""

from datetime import UTC, datetime

import httpx

from app.config import settings
from app.services.weather_apis.base import (
    BaseWeatherClient,
    ForecastPeriod,
    WeatherAlert,
    WeatherData,
)

# WMO Weather interpretation codes (WW)
# https://open-meteo.com/en/docs#weathervariables
WMO_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class OpenMeteoClient(BaseWeatherClient):
    """
    Client for Open-Meteo API.

    No API key required. Free for non-commercial use.
    Coverage: Global
    """

    def __init__(self):
        """Initialize Open-Meteo client."""
        super().__init__(
            base_url=settings.OPEN_METEO_API_BASE_URL,
            name="open-meteo",
        )
        self.timeout = 30.0

    async def get_current_weather(
        self, latitude: float, longitude: float
    ) -> WeatherData:
        """
        Get current weather from Open-Meteo.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            WeatherData object with current conditions

        Raises:
            ValueError: If coordinates are invalid
            Exception: If API request fails
        """
        self.validate_coordinates(latitude, longitude)

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
            ]),
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/forecast"
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return self._parse_current(data)

    def _parse_current(self, data: dict) -> WeatherData:
        """
        Parse Open-Meteo response into normalized WeatherData.

        Args:
            data: Raw API response

        Returns:
            WeatherData object
        """
        current = data["current"]

        temp_c = current.get("temperature_2m")
        temp_f = self._celsius_to_fahrenheit(temp_c) if temp_c is not None else None

        weather_code = current.get("weather_code", 0)
        condition_text = WMO_WEATHER_CODES.get(weather_code, "Unknown")

        timestamp_str = current.get("time")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=UTC)
        else:
            timestamp = datetime.now(UTC)

        humidity = current.get("relative_humidity_2m")
        if humidity is not None:
            humidity = int(humidity)

        cloud_cover = current.get("cloud_cover")
        if cloud_cover is not None:
            cloud_cover = int(cloud_cover)

        return WeatherData(
            temperature=temp_c,
            temperature_fahrenheit=temp_f,
            timestamp=timestamp,
            condition_text=condition_text,
            humidity=humidity,
            pressure=current.get("pressure_msl"),
            wind_speed=current.get("wind_speed_10m"),
            wind_direction=int(current["wind_direction_10m"])
            if current.get("wind_direction_10m") is not None
            else None,
            wind_gust=current.get("wind_gusts_10m"),
            feels_like=current.get("apparent_temperature"),
            cloud_cover=cloud_cover,
            precipitation=current.get("precipitation"),
            condition_code=str(weather_code),
            raw_data=data,
        )

    async def get_alerts(
        self, latitude: float, longitude: float
    ) -> list[WeatherAlert]:
        """
        Get weather alerts. Open-Meteo does not provide alerts.

        Returns:
            Empty list (alerts not supported)
        """
        return []

    async def get_forecast(
        self, latitude: float, longitude: float
    ) -> list[ForecastPeriod]:
        """
        Get forecast. Not yet implemented for Open-Meteo.

        Returns:
            Empty list
        """
        return []

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return (celsius * 9 / 5) + 32
