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
        Get daily forecast from Open-Meteo (7 days).

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            List of ForecastPeriod objects (one per day)
        """
        self.validate_coordinates(latitude, longitude)

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join([
                "temperature_2m_max",
                "temperature_2m_min",
                "apparent_temperature_max",
                "apparent_temperature_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "weather_code",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "wind_direction_10m_dominant",
                "relative_humidity_2m_max",
                "uv_index_max",
            ]),
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
            "timezone": "UTC",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            url = f"{self.base_url}/forecast"
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return self._parse_daily_forecast(data)

    def _parse_daily_forecast(self, data: dict) -> list[ForecastPeriod]:
        """
        Parse Open-Meteo daily forecast response into ForecastPeriod list.

        Args:
            data: Raw API response with "daily" key

        Returns:
            List of ForecastPeriod objects
        """
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        periods = []

        for i, date_str in enumerate(dates):
            start = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            # Each daily period covers a full day
            end = start.replace(hour=23, minute=59, second=59)

            temp_max = daily.get("temperature_2m_max", [None])[i]
            temp_min = daily.get("temperature_2m_min", [None])[i]
            feels_max = daily.get("apparent_temperature_max", [None])[i]

            temp_max_f = (
                self._celsius_to_fahrenheit(temp_max) if temp_max is not None else None
            )
            temp_min_f = (
                self._celsius_to_fahrenheit(temp_min) if temp_min is not None else None
            )

            weather_code = daily.get("weather_code", [None])[i]
            condition_text = (
                WMO_WEATHER_CODES.get(weather_code, "Unknown")
                if weather_code is not None
                else None
            )

            precip_prob = daily.get("precipitation_probability_max", [None])[i]
            if precip_prob is not None:
                precip_prob = int(precip_prob)

            humidity = daily.get("relative_humidity_2m_max", [None])[i]
            if humidity is not None:
                humidity = int(humidity)

            uv_index = daily.get("uv_index_max", [None])[i]

            periods.append(
                ForecastPeriod(
                    start_time=start,
                    end_time=end,
                    temperature=temp_max,
                    temperature_fahrenheit=temp_max_f,
                    temp_low=temp_min,
                    temp_low_fahrenheit=temp_min_f,
                    feels_like=feels_max,
                    humidity=humidity,
                    wind_speed=daily.get("wind_speed_10m_max", [None])[i],
                    wind_gust=daily.get("wind_gusts_10m_max", [None])[i],
                    wind_direction=self._safe_int(
                        daily.get("wind_direction_10m_dominant", [None])[i]
                    ),
                    precipitation_probability=precip_prob,
                    precipitation_amount=daily.get("precipitation_sum", [None])[i],
                    uv_index=uv_index,
                    condition_text=condition_text,
                    condition_code=str(weather_code) if weather_code is not None else None,
                    is_daytime=True,  # Daily summary represents the full day
                )
            )

        return periods

    @staticmethod
    def _safe_int(value) -> int | None:
        """Convert a value to int if not None."""
        return int(value) if value is not None else None

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return (celsius * 9 / 5) + 32
