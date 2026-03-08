"""
Redis output backend implementation.
"""

import logging

import redis.asyncio as aioredis

from app.models.location import Location
from app.services.outputs.base import BaseOutputBackend, WriteResult
from app.services.outputs.formats.kurokku import KurokuuFormatTransform
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = logging.getLogger(__name__)

FORMAT_TRANSFORMS = {
    "kurokku": KurokuuFormatTransform,
}


class RedisOutputBackend(BaseOutputBackend):
    """
    Output backend that writes weather data to Redis.

    Delegates key/value formatting to a pluggable format transform.
    """

    def __init__(
        self,
        name: str,
        config: dict,
        format_type: str | None = None,
        format_config: dict | None = None,
    ):
        """
        Initialize the Redis output backend.

        Args:
            name: Backend instance name
            config: Connection config with 'url' key
            format_type: Format transform type (e.g., 'kurokku')
            format_config: Format-specific configuration
        """
        super().__init__(name=name, config=config)
        self._client: aioredis.Redis | None = None

        # Set up format transform
        transform_cls = FORMAT_TRANSFORMS.get(format_type or "")
        if transform_cls:
            self.transform = transform_cls(format_config)
        else:
            self.transform = None

    def _get_client(self) -> aioredis.Redis:
        """Get or create Redis async client."""
        if self._client is None:
            url = self.config.get("url", "redis://localhost:6379/0")
            self._client = aioredis.from_url(
                url,
                decode_responses=True,
                socket_timeout=self.config.get("timeout", 10),
                socket_connect_timeout=self.config.get("connect_timeout", 5),
            )
        return self._client

    async def write(
        self,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> WriteResult:
        """
        Write weather data and alerts to Redis.

        Args:
            location: Location model instance
            weather_data: Normalized weather data
            alerts: List of active weather alerts

        Returns:
            WriteResult with operation details
        """
        if not self.transform:
            return WriteResult(
                success=False,
                backend_name=self.name,
                errors=["No format transform configured"],
            )

        client = self._get_client()
        keys_written = 0
        keys_deleted = 0
        errors = []

        # Write weather data (temperature, humidity, conditions)
        for label, method in [
            ("Temperature", self.transform.format_temperature),
            ("Humidity", self.transform.format_humidity),
            ("Conditions", self.transform.format_conditions),
        ]:
            try:
                entries = method(location, weather_data)
                for key, value, ttl in entries:
                    await client.set(key, value, ex=ttl)
                    keys_written += 1
            except Exception as e:
                errors.append(f"{label} write failed: {e}")
                logger.error(
                    "Failed to write %s to Redis for %s: %s",
                    label.lower(),
                    location.name,
                    e,
                )

        # Write alerts
        try:
            delete_patterns, alert_entries = self.transform.format_alerts(
                location, alerts
            )

            # Delete old alert keys
            for pattern in delete_patterns:
                async for key in client.scan_iter(match=pattern):
                    await client.delete(key)
                    keys_deleted += 1

            # Write new alert keys
            for key, value, ttl in alert_entries:
                await client.set(key, value, ex=ttl)
                keys_written += 1
        except Exception as e:
            errors.append(f"Alert write failed: {e}")
            logger.error(
                "Failed to write alerts to Redis for %s: %s",
                location.name,
                e,
            )

        success = len(errors) == 0
        return WriteResult(
            success=success,
            backend_name=self.name,
            keys_written=keys_written,
            keys_deleted=keys_deleted,
            errors=errors,
        )

    async def test_connection(self) -> bool:
        """Test Redis connectivity."""
        try:
            client = self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.error("Redis connection test failed for %s: %s", self.name, e)
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
