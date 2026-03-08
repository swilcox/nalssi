"""
Unit tests for Redis output backend.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.outputs.redis_backend import RedisOutputBackend
from app.services.weather_apis.base import WeatherAlert, WeatherData


def _make_location(slug="spring_hill", name="Spring Hill"):
    loc = MagicMock()
    loc.slug = slug
    loc.name = name
    return loc


def _make_weather(temp_f=44.0, temp_c=6.7):
    return WeatherData(
        temperature=temp_c,
        temperature_fahrenheit=temp_f,
        timestamp=datetime.now(UTC),
        condition_text="Clear",
    )


def _make_alert(event="Severe Thunderstorm Warning", hours_until_expiry=2):
    now = datetime.now(UTC)
    return WeatherAlert(
        event=event,
        headline=f"{event} issued",
        description="Test alert description",
        severity="Severe",
        urgency="Immediate",
        effective=now - timedelta(hours=1),
        expires=now + timedelta(hours=hours_until_expiry),
        areas=["Test County"],
    )


@pytest.mark.unit
class TestRedisOutputBackend:
    """Tests for RedisOutputBackend."""

    def test_no_transform_returns_failure(self):
        """Backend without format transform should return failure."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type=None,
        )
        assert backend.transform is None

    @pytest.mark.asyncio
    async def test_write_without_transform(self):
        """Write should fail gracefully without a transform."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
        )
        location = _make_location()
        result = await backend.write(location, _make_weather(), [])

        assert result.success is False
        assert "No format transform configured" in result.errors[0]

    @pytest.mark.asyncio
    async def test_write_temperature(self):
        """Test writing temperature to Redis."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )

        # Mock the Redis client
        mock_client = AsyncMock()
        backend._client = mock_client
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([]))

        location = _make_location(slug="spring_hill")
        weather = _make_weather(temp_f=44.0)

        result = await backend.write(location, weather, [])

        assert result.success is True
        assert result.keys_written == 3  # temp + humidity + conditions
        mock_client.set.assert_any_call(
            "kurokku:weather:spring_hill:temp", "44°F", ex=3600
        )
        mock_client.set.assert_any_call(
            "kurokku:weather:spring_hill:humidity", "--%", ex=3600
        )
        mock_client.set.assert_any_call(
            "kurokku:weather:spring_hill:conditions", "Clear", ex=3600
        )

    @pytest.mark.asyncio
    async def test_write_alerts(self):
        """Test writing alerts to Redis."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )

        mock_client = AsyncMock()
        backend._client = mock_client
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([]))

        location = _make_location(slug="test_loc")
        alerts = [_make_alert(event="Tornado Warning")]

        result = await backend.write(location, None, alerts)

        # 1 alert key (no temperature since weather_data is None but slug exists so --°F is written)
        assert result.success is True
        assert result.keys_written >= 1

    @pytest.mark.asyncio
    async def test_write_deletes_old_alerts(self):
        """Test that old alert keys are deleted before writing new ones."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )

        mock_client = AsyncMock()
        backend._client = mock_client
        # Simulate existing keys
        mock_client.scan_iter = MagicMock(
            return_value=AsyncIterator(
                [
                    "kurokku:alert:weather:test:0",
                    "kurokku:alert:weather:test:1",
                ]
            )
        )

        location = _make_location(slug="test")
        result = await backend.write(location, None, [])

        assert result.keys_deleted == 2

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Test successful connection test."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
        )
        mock_client = AsyncMock()
        backend._client = mock_client
        mock_client.ping.return_value = True

        assert await backend.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Test failed connection test."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
        )
        mock_client = AsyncMock()
        backend._client = mock_client
        mock_client.ping.side_effect = ConnectionError("Connection refused")

        assert await backend.test_connection() is False

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the backend."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
        )
        mock_client = AsyncMock()
        backend._client = mock_client

        await backend.close()
        mock_client.aclose.assert_called_once()
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_write_handles_redis_error(self):
        """Test that Redis errors are caught per-operation."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )

        mock_client = AsyncMock()
        backend._client = mock_client
        mock_client.set.side_effect = ConnectionError("Connection lost")
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([]))

        location = _make_location()
        result = await backend.write(location, _make_weather(), [])

        assert result.success is False
        assert len(result.errors) > 0


class AsyncIterator:
    """Helper to create an async iterator from a list for mocking scan_iter."""

    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)
