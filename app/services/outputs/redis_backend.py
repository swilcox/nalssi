"""
Redis output backend implementation.
"""

from collections.abc import Awaitable
from typing import cast

import redis.asyncio as aioredis
import structlog

from app.models.location import Location
from app.services.outputs.base import BaseOutputBackend, WriteResult
from app.services.outputs.formats.kurokku import KurokuuFormatTransform
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = structlog.get_logger()

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
            self.transform: KurokuuFormatTransform | None = transform_cls(format_config)
        else:
            self.transform = None

    def _get_client(self) -> aioredis.Redis:
        """Get or create Redis async client."""
        if self._client is None:
            url = self.config.get("url", "redis://localhost:6379/0")
            self._client = aioredis.from_url(
                url,
                decode_responses=True,
                socket_timeout=self.config.get("timeout", 3),
                socket_connect_timeout=self.config.get("connect_timeout", 2),
            )
        return self._client

    # Refresh an existing key's TTL only when it's drifted by more than this
    # many seconds. The TTL we compute is `expires - now`, which decreases by
    # ~one collection interval each cycle even when the alert is unchanged;
    # tolerating a small drift avoids issuing an EXPIRE every cycle.
    _TTL_REFRESH_THRESHOLD_S = 60

    async def write(
        self,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert] | None,
    ) -> WriteResult:
        """
        Write weather data and alerts to Redis.

        Alert syncing is diff-based: only keys that changed are written, only
        keys that disappeared upstream are deleted, and unchanged keys whose
        TTL has drifted significantly get an EXPIRE refresh. ``alerts=None``
        signals an upstream fetch failure — alert keys are left untouched.
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

        # Sync alerts. When alerts is None the upstream fetch failed, so leave
        # whatever keys are already in Redis alone — they'll TTL out naturally.
        if alerts is not None:
            try:
                w, d = await self._sync_alerts(client, location, alerts)
                keys_written += w
                keys_deleted += d
            except Exception as e:
                errors.append(f"Alert sync failed: {e}")
                logger.error(
                    "Failed to sync alerts to Redis for %s: %s",
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

    async def _sync_alerts(
        self,
        client: aioredis.Redis,
        location: Location,
        alerts: list[WeatherAlert],
    ) -> tuple[int, int]:
        """
        Reconcile Redis alert keys with the desired set from the transform.

        Returns:
            Tuple of (keys_written, keys_deleted). Unchanged keys (same value,
            similar TTL) are not counted in either — they cost only a GET.
        """
        assert self.transform is not None
        prefix, desired = self.transform.format_alerts(location, alerts)
        if not prefix:
            return 0, 0

        existing_keys: set[str] = set()
        async for key in client.scan_iter(match=f"{prefix}*"):
            existing_keys.add(key)

        desired_keys = set(desired.keys())
        keys_written = 0
        keys_deleted = 0

        # Delete keys for alerts that disappeared upstream.
        for key in existing_keys - desired_keys:
            await client.delete(key)
            keys_deleted += 1

        for key, (value, ttl) in desired.items():
            if key in existing_keys:
                existing_value = await client.get(key)
                if existing_value == value:
                    # Value unchanged. Refresh TTL only if the wall-clock
                    # expiry has shifted enough to matter (e.g. NOAA extended
                    # the alert), so we don't spam EXPIRE every cycle.
                    current_ttl = await client.ttl(key)
                    if (
                        current_ttl is None
                        or current_ttl < 0
                        or abs(ttl - current_ttl) > self._TTL_REFRESH_THRESHOLD_S
                    ):
                        await client.expire(key, ttl)
                    continue
            await client.set(key, value, ex=ttl)
            keys_written += 1

        return keys_written, keys_deleted

    async def test_connection(self) -> bool:
        """Test Redis connectivity."""
        try:
            client = self._get_client()
            result = client.ping()
            if isinstance(result, Awaitable):
                result = await cast(Awaitable[bool], result)
            return bool(result)
        except Exception as e:
            logger.error("Redis connection test failed for %s: %s", self.name, e)
            return False

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            result = self._client.aclose()
            if isinstance(result, Awaitable):
                await result
            self._client = None
