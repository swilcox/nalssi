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


def _make_alert(
    event="Severe Thunderstorm Warning", hours_until_expiry=2, alert_id=None
):
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
        alert_id=alert_id or f"urn:test:{event}",
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
    async def test_alerts_none_skips_alert_sync(self):
        """alerts=None signals upstream fetch failure: existing alert keys must
        be left alone (no scan, no delete, no set)."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )
        mock_client = AsyncMock()
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([]))
        backend._client = mock_client

        location = _make_location(slug="test_loc")
        result = await backend.write(location, _make_weather(), None)

        assert result.success is True
        # scan_iter should not have been called for alerts at all
        mock_client.scan_iter.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_alert_does_not_set(self):
        """If an existing key holds the exact value we'd write, skip SET so the
        kurokku device doesn't see spurious key-change events."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )
        location = _make_location(slug="test")
        alert = _make_alert(event="Tornado Warning", alert_id="urn:test:t1")

        # Compute what the format would emit so we can pre-populate the mock.
        prefix, desired = backend.transform.format_alerts(location, [alert])
        (existing_key, (existing_value, existing_ttl)) = next(iter(desired.items()))

        mock_client = AsyncMock()
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([existing_key]))
        mock_client.get.return_value = existing_value
        # TTL within the refresh threshold — should not trigger EXPIRE either.
        mock_client.ttl.return_value = existing_ttl
        backend._client = mock_client

        result = await backend.write(location, None, [alert])

        # No alert SETs (only the 3 weather-data SETs).
        alert_sets = [
            c for c in mock_client.set.call_args_list if c.args[0].startswith(prefix)
        ]
        assert alert_sets == []
        mock_client.delete.assert_not_called()
        mock_client.expire.assert_not_called()
        # Bookkeeping: no churn for the unchanged alert.
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unchanged_alert_refreshes_drifted_ttl(self):
        """When the value matches but TTL drifted (NOAA extended the alert),
        EXPIRE refreshes it without re-SETting."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )
        location = _make_location(slug="test")
        alert = _make_alert(
            event="Tornado Warning", hours_until_expiry=2, alert_id="urn:test:t1"
        )
        prefix, desired = backend.transform.format_alerts(location, [alert])
        (existing_key, (existing_value, _ttl)) = next(iter(desired.items()))

        mock_client = AsyncMock()
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([existing_key]))
        mock_client.get.return_value = existing_value
        mock_client.ttl.return_value = 60  # way below the desired ~7200
        backend._client = mock_client

        await backend.write(location, None, [alert])

        mock_client.expire.assert_called_once()
        alert_sets = [
            c for c in mock_client.set.call_args_list if c.args[0].startswith(prefix)
        ]
        assert alert_sets == []

    @pytest.mark.asyncio
    async def test_changed_alert_triggers_set(self):
        """If the desired value differs from what's stored, SET overwrites it."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )
        location = _make_location(slug="test")
        alert = _make_alert(event="Tornado Warning", alert_id="urn:test:t1")
        prefix, desired = backend.transform.format_alerts(location, [alert])
        existing_key = next(iter(desired))

        mock_client = AsyncMock()
        mock_client.scan_iter = MagicMock(return_value=AsyncIterator([existing_key]))
        mock_client.get.return_value = '{"message":"old payload"}'
        backend._client = mock_client

        result = await backend.write(location, None, [alert])

        alert_sets = [
            c for c in mock_client.set.call_args_list if c.args[0].startswith(prefix)
        ]
        assert len(alert_sets) == 1
        assert result.keys_written >= 1

    @pytest.mark.asyncio
    async def test_orphan_alerts_deleted(self):
        """Existing keys with no corresponding upstream alert get deleted."""
        backend = RedisOutputBackend(
            name="test",
            config={"url": "redis://localhost:6379/0"},
            format_type="kurokku",
        )
        location = _make_location(slug="test")
        alert = _make_alert(event="Tornado Warning", alert_id="urn:test:t1")
        prefix, desired = backend.transform.format_alerts(location, [alert])
        kept_key = next(iter(desired))
        orphan_key = f"{prefix}deadbeef0000"

        mock_client = AsyncMock()
        mock_client.scan_iter = MagicMock(
            return_value=AsyncIterator([kept_key, orphan_key])
        )
        mock_client.get.return_value = next(iter(desired.values()))[0]
        mock_client.ttl.return_value = next(iter(desired.values()))[1]
        backend._client = mock_client

        result = await backend.write(location, None, [alert])

        mock_client.delete.assert_called_once_with(orphan_key)
        assert result.keys_deleted == 1

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
