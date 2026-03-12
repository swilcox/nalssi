"""
NOAA (National Weather Service) API client.

Documentation: https://www.weather.gov/documentation/services-web-api
"""

from datetime import UTC, datetime

import httpx

from app.config import settings
from app.services.weather_apis.base import (
    BaseWeatherClient,
    WeatherAlert,
    WeatherData,
)


class NOAAWeatherClient(BaseWeatherClient):
    """
    Client for NOAA Weather.gov API.

    No API key required. Free for all use.
    Coverage: United States only
    """

    def __init__(self):
        """Initialize NOAA client."""
        super().__init__(
            base_url=settings.NOAA_API_BASE_URL,
            name="noaa",
        )
        self.timeout = httpx.Timeout(60.0, connect=10.0)

    def _get_headers(self) -> dict:
        """
        Get HTTP headers for NOAA API requests.

        NOAA requires a User-Agent header identifying the application.
        """
        return {
            "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION} (Weather Data Collection Service)",
            "Accept": "application/json",
        }

    async def get_current_weather(
        self, latitude: float, longitude: float
    ) -> WeatherData:
        """
        Get current weather from NOAA.

        Process:
        1. Get gridpoint data for lat/lon
        2. Get observation stations for gridpoint
        3. Get latest observation from nearest station

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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Step 1: Get gridpoint data
            points_url = f"{self.base_url}/points/{latitude},{longitude}"
            response = await client.get(points_url, headers=self._get_headers())
            response.raise_for_status()
            points_data = response.json()

            # Step 2: Get observation stations
            stations_url = points_data["properties"]["observationStations"]
            response = await client.get(stations_url, headers=self._get_headers())
            response.raise_for_status()
            stations_data = response.json()

            # Try stations in order until we find one with valid temperature
            features = stations_data.get("features", [])
            if not features:
                raise Exception("No observation stations found for location")

            max_stations = min(len(features), 5)
            last_obs_data = None

            for i in range(max_stations):
                station_url = features[i]["id"]
                obs_url = f"{station_url}/observations/latest"

                try:
                    response = await client.get(
                        obs_url, headers=self._get_headers()
                    )
                    response.raise_for_status()
                    obs_data = response.json()
                    last_obs_data = obs_data

                    # Check if temperature has a valid value
                    temp_data = obs_data.get("properties", {}).get("temperature")
                    if temp_data and temp_data.get("value") is not None:
                        return self._parse_observation(obs_data)
                except httpx.HTTPError:
                    continue

            # Fall back to last observation even with null temperature
            if last_obs_data:
                return self._parse_observation(last_obs_data)

            raise Exception(
                f"No valid observations from {max_stations} nearest stations"
            )

    def _parse_observation(self, obs_data: dict) -> WeatherData:
        """
        Parse NOAA observation data into normalized WeatherData.

        Args:
            obs_data: Raw observation data from NOAA API

        Returns:
            WeatherData object
        """
        props = obs_data["properties"]

        # Extract temperature (NOAA provides in Celsius)
        temp_c = self._get_value(props.get("temperature"))
        temp_f = self._celsius_to_fahrenheit(temp_c) if temp_c is not None else None

        # Extract other measurements
        humidity = self._get_value(props.get("relativeHumidity"))
        if humidity is not None:
            humidity = int(humidity)

        # Convert pressure from Pa to hPa
        pressure_pa = self._get_value(props.get("barometricPressure"))
        pressure_hpa = pressure_pa / 100 if pressure_pa is not None else None

        # Wind data
        wind_speed = self._get_value(props.get("windSpeed"))
        wind_direction = self._get_value(props.get("windDirection"))
        if wind_direction is not None:
            wind_direction = int(wind_direction)

        wind_gust = self._get_value(props.get("windGust"))
        visibility = self._get_value(props.get("visibility"))
        if visibility is not None:
            visibility = int(visibility)

        # Parse timestamp
        timestamp_str = props.get("timestamp")
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).astimezone(UTC)
            if timestamp_str
            else datetime.now(UTC)
        )

        # Condition text
        condition_text = props.get("textDescription", "Unknown")

        return WeatherData(
            temperature=temp_c,
            temperature_fahrenheit=temp_f,
            timestamp=timestamp,
            condition_text=condition_text,
            humidity=humidity,
            pressure=pressure_hpa,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            wind_gust=wind_gust,
            visibility=visibility,
            icon=props.get("icon"),
            raw_data=obs_data,
        )

    async def get_alerts(self, latitude: float, longitude: float) -> list[WeatherAlert]:
        """
        Get active weather alerts from NOAA.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            List of active WeatherAlert objects

        Raises:
            ValueError: If coordinates are invalid
            Exception: If API request fails
        """
        self.validate_coordinates(latitude, longitude)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Get active alerts for the point
            alerts_url = f"{self.base_url}/alerts/active"
            params = {"point": f"{latitude},{longitude}"}

            response = await client.get(
                alerts_url, params=params, headers=self._get_headers()
            )
            response.raise_for_status()
            alerts_data = response.json()

            # Parse alerts
            alerts = []
            for feature in alerts_data.get("features", []):
                alert = self._parse_alert(feature)
                if alert:
                    alerts.append(alert)

            return alerts

    def _parse_alert(self, feature: dict) -> WeatherAlert:
        """
        Parse NOAA alert feature into WeatherAlert.

        NOAA returns alerts in GeoJSON with CAP-derived properties.

        Args:
            feature: Alert feature from NOAA API

        Returns:
            WeatherAlert object
        """
        props = feature["properties"]

        # Parse timestamps and convert to UTC so SQLite stores correct values
        effective = self._parse_timestamp(props.get("effective"))
        expires = self._parse_timestamp(props.get("expires"))
        onset = self._parse_timestamp(props.get("onset"))
        ends = self._parse_timestamp(props.get("ends"))

        # Get areas affected
        areas = [props.get("areaDesc", "Unknown")]

        # CAP category can be a list in the NOAA response; join if so
        raw_category = props.get("category")
        if isinstance(raw_category, list):
            category = ", ".join(raw_category) if raw_category else None
        else:
            category = raw_category

        # response can also be a list
        raw_response = props.get("response")
        if isinstance(raw_response, list):
            response_type = ", ".join(raw_response) if raw_response else None
        else:
            response_type = raw_response

        return WeatherAlert(
            alert_id=props.get("id"),
            event=props.get("event", "Unknown"),
            headline=props.get("headline", ""),
            description=props.get("description", ""),
            instruction=props.get("instruction"),
            severity=props.get("severity", "Unknown"),
            urgency=props.get("urgency", "Unknown"),
            certainty=props.get("certainty"),
            category=category,
            response_type=response_type,
            sender_name=props.get("senderName"),
            status=props.get("status"),
            message_type=props.get("messageType"),
            effective=effective,
            expires=expires,
            onset=onset,
            ends=ends,
            areas=areas,
        )

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        """Parse an ISO timestamp string to a UTC datetime, or None."""
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)

    @staticmethod
    def _get_value(data: dict) -> float | None:
        """
        Extract value from NOAA's unit-aware data structure.

        Args:
            data: Dictionary with 'value' and 'unitCode' keys

        Returns:
            The numeric value, or None if not present
        """
        if data is None:
            return None
        return data.get("value")

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return (celsius * 9 / 5) + 32
