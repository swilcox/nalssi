"""
InfluxDB output backend implementation.
"""

import structlog
from influxdb_client import WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write.point import Point

from app.config import settings
from app.models.location import Location
from app.services.outputs.base import BaseOutputBackend, WriteResult
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = structlog.get_logger()

# WeatherData fields to write as InfluxDB fields (name -> type hint for int vs float)
_WEATHER_FIELDS = {
    "temperature": float,
    "temperature_fahrenheit": float,
    "humidity": int,
    "pressure": float,
    "wind_speed": float,
    "wind_direction": int,
    "wind_gust": float,
    "feels_like": float,
    "precipitation": float,
    "cloud_cover": int,
    "visibility": int,
    "uv_index": int,
}


class InfluxDBOutputBackend(BaseOutputBackend):
    """
    Output backend that writes weather data to InfluxDB.

    Writes weather observations as points in the 'weather' measurement
    and alerts as points in the 'weather_alert' measurement.
    """

    def __init__(
        self,
        name: str,
        config: dict,
        format_type: str | None = None,
        format_config: dict | None = None,
    ):
        super().__init__(name=name, config=config)
        self._client: InfluxDBClientAsync | None = None
        self._url = config.get("url") or settings.INFLUXDB_URL
        self._token = config.get("token") or settings.INFLUXDB_TOKEN
        self._org = config.get("org") or settings.INFLUXDB_ORG
        self._bucket = config.get("bucket") or settings.INFLUXDB_BUCKET
        self._timeout = config.get("timeout", 10_000)

    def _get_client(self) -> InfluxDBClientAsync:
        """Get or create the async InfluxDB client."""
        if self._client is None:
            self._client = InfluxDBClientAsync(
                url=self._url,
                token=self._token,
                org=self._org,
                timeout=self._timeout,
            )
        return self._client

    def _build_weather_point(
        self, location: Location, weather_data: WeatherData
    ) -> Point:
        """Build an InfluxDB Point from weather data."""
        point = (
            Point("weather")
            .tag("location", location.slug or location.name)
            .tag("country", location.country_code)
        )

        # Add source if available from raw_data
        source = None
        if weather_data.raw_data and "source" in weather_data.raw_data:
            source = weather_data.raw_data["source"]
        if source:
            point = point.tag("source", source)

        # Add numeric fields, skipping None values
        for field_name, field_type in _WEATHER_FIELDS.items():
            value = getattr(weather_data, field_name, None)
            if value is not None:
                if field_type is int:
                    point = point.field(field_name, int(value))
                else:
                    point = point.field(field_name, float(value))

        # Add condition as string field
        if weather_data.condition_text:
            point = point.field("condition", weather_data.condition_text)

        point = point.time(weather_data.timestamp, WritePrecision.S)
        return point

    def _build_alert_point(self, location: Location, alert: WeatherAlert) -> Point:
        """Build an InfluxDB Point from a weather alert."""
        point = (
            Point("weather_alert")
            .tag("location", location.slug or location.name)
            .tag("severity", alert.severity.lower())
            .tag("event", alert.event)
            .field("headline", alert.headline)
            .field("urgency", alert.urgency)
            .field("areas", ", ".join(alert.areas) if alert.areas else "")
            .field("active", 1)
            .time(alert.effective, WritePrecision.S)
        )
        return point

    async def write(
        self,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> WriteResult:
        """Write weather data and alerts to InfluxDB."""
        points: list[Point] = []

        if weather_data is not None:
            points.append(self._build_weather_point(location, weather_data))

        for alert in alerts:
            points.append(self._build_alert_point(location, alert))

        if not points:
            return WriteResult(
                success=True,
                backend_name=self.name,
                keys_written=0,
            )

        try:
            client = self._get_client()
            write_api = client.write_api()
            await write_api.write(
                bucket=self._bucket,
                record=points,
            )
            return WriteResult(
                success=True,
                backend_name=self.name,
                keys_written=len(points),
            )
        except Exception as e:
            logger.error("Failed to write to InfluxDB for %s: %s", location.name, e)
            return WriteResult(
                success=False,
                backend_name=self.name,
                errors=[str(e)],
            )

    async def test_connection(self) -> bool:
        """Test InfluxDB connectivity."""
        try:
            client = self._get_client()
            return await client.ping()
        except Exception as e:
            logger.error("InfluxDB connection test failed for %s: %s", self.name, e)
            return False

    async def close(self) -> None:
        """Close the InfluxDB client."""
        if self._client:
            await self._client.close()
            self._client = None
