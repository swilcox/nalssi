"""
OpenWeatherMap API client.

Documentation: https://openweathermap.org/current
Free tier: 1,000 calls/day with API key. Global coverage.
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


class OpenWeatherClient(BaseWeatherClient):
    """
    Client for OpenWeatherMap API.

    Requires a free API key. Free tier: 1,000 calls/day.
    Coverage: Global
    """

    def __init__(self):
        """Initialize OpenWeather client."""
        super().__init__(
            base_url=settings.OPENWEATHER_API_BASE_URL,
            name="openweather",
        )
        self.api_key = settings.OPENWEATHER_API_KEY
        self.timeout = 30.0

    async def get_current_weather(
        self, latitude: float, longitude: float
    ) -> WeatherData:
        """
        Get current weather from OpenWeatherMap.

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
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/weather"
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return self._parse_weather(data)

    def _parse_weather(self, data: dict) -> WeatherData:
        """
        Parse OpenWeatherMap response into normalized WeatherData.

        Args:
            data: Raw API response

        Returns:
            WeatherData object
        """
        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        weather_info = data.get("weather", [{}])[0]
        temp_c = main.get("temp")
        temp_f = self._celsius_to_fahrenheit(temp_c) if temp_c is not None else None

        # Precipitation: check rain.1h, then snow.1h
        precipitation = None
        rain = data.get("rain")
        if rain:
            precipitation = rain.get("1h", 0.0)
        else:
            snow = data.get("snow")
            if snow:
                precipitation = snow.get("1h", 0.0)

        # Parse timestamp
        dt = data.get("dt")
        timestamp = datetime.fromtimestamp(dt, tz=UTC) if dt else datetime.now(UTC)

        # Wind direction
        wind_direction = wind.get("deg")
        if wind_direction is not None:
            wind_direction = int(wind_direction)

        # Visibility (OWM provides in meters)
        visibility = data.get("visibility")
        if visibility is not None:
            visibility = int(visibility)

        return WeatherData(
            temperature=temp_c,
            temperature_fahrenheit=temp_f,
            timestamp=timestamp,
            condition_text=weather_info.get("description", "Unknown"),
            condition_code=str(weather_info.get("id", "")),
            icon=weather_info.get("icon"),
            humidity=int(main["humidity"]) if main.get("humidity") is not None else None,
            pressure=main.get("pressure"),
            wind_speed=wind.get("speed"),
            wind_direction=wind_direction,
            wind_gust=wind.get("gust"),
            feels_like=main.get("feels_like"),
            visibility=visibility,
            cloud_cover=int(clouds["all"]) if clouds.get("all") is not None else None,
            precipitation=precipitation,
            raw_data=data,
        )

    async def get_alerts(
        self, latitude: float, longitude: float
    ) -> list[WeatherAlert]:
        """
        Get weather alerts. Requires paid One Call API — not supported in free tier.

        Returns:
            Empty list (alerts not supported in free tier)
        """
        return []

    async def get_forecast(
        self, latitude: float, longitude: float
    ) -> list[ForecastPeriod]:
        """
        Get forecast. Not yet implemented for OpenWeatherMap.

        Returns:
            Empty list
        """
        return []

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return (celsius * 9 / 5) + 32
