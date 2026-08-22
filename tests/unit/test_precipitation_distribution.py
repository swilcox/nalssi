"""
Tests for radar precipitation state reaching the output backends.

Covers the collector's lookup (including every path that yields "unknown") and
the plumbing through OutputManager into the Redis and InfluxDB backends.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.location import Location
from app.services.collectors import weather_collector as wc
from app.services.collectors.weather_collector import WeatherCollector
from app.services.outputs.formats.kurokku import KurokuuFormatTransform
from app.services.outputs.manager import OutputManager


@pytest.fixture
def us_location():
    return Location(
        name="Minneapolis",
        slug="minneapolis",
        latitude=44.98,
        longitude=-93.27,
        country_code="US",
    )


@pytest.fixture
def foreign_location():
    return Location(
        name="London",
        slug="london",
        latitude=51.5,
        longitude=-0.12,
        country_code="GB",
    )


class TestCollectorPrecipitationLookup:
    async def test_returns_radar_result_when_enabled(self, us_location):
        collector = WeatherCollector()
        client = MagicMock()
        client.precip_at = AsyncMock(return_value=True)

        with (
            patch.object(wc, "settings", SimpleNamespace(RADAR_ENABLED=True)),
            patch(
                "app.services.collectors.weather_collector.get_radar_client",
                return_value=client,
            ),
        ):
            assert await collector._get_precipitation(us_location) is True

        # The collector resolves the location to its national radar source.
        awaited_lat, awaited_lon, awaited_source = client.precip_at.await_args.args
        assert (awaited_lat, awaited_lon) == (44.98, -93.27)
        assert awaited_source.name == "conus"

    async def test_returns_false_when_radar_is_clear(self, us_location):
        collector = WeatherCollector()
        client = MagicMock()
        client.precip_at = AsyncMock(return_value=False)

        with (
            patch.object(wc, "settings", SimpleNamespace(RADAR_ENABLED=True)),
            patch(
                "app.services.collectors.weather_collector.get_radar_client",
                return_value=client,
            ),
        ):
            assert await collector._get_precipitation(us_location) is False

    async def test_unknown_when_radar_disabled(self, us_location):
        collector = WeatherCollector()
        client = MagicMock()
        client.precip_at = AsyncMock(return_value=True)

        with (
            patch.object(wc, "settings", SimpleNamespace(RADAR_ENABLED=False)),
            patch(
                "app.services.collectors.weather_collector.get_radar_client",
                return_value=client,
            ),
        ):
            assert await collector._get_precipitation(us_location) is None

        client.precip_at.assert_not_awaited()

    async def test_unknown_outside_radar_coverage(self, foreign_location):
        collector = WeatherCollector()
        client = MagicMock()
        client.precip_at = AsyncMock(return_value=True)

        with (
            patch.object(wc, "settings", SimpleNamespace(RADAR_ENABLED=True)),
            patch(
                "app.services.collectors.weather_collector.get_radar_client",
                return_value=client,
            ),
        ):
            assert await collector._get_precipitation(foreign_location) is None

        client.precip_at.assert_not_awaited()

    async def test_unknown_when_lookup_fails(self, us_location):
        """A radar outage must not be reported as 'dry'."""
        collector = WeatherCollector()
        client = MagicMock()
        client.precip_at = AsyncMock(side_effect=RuntimeError("upstream down"))

        with (
            patch.object(wc, "settings", SimpleNamespace(RADAR_ENABLED=True)),
            patch(
                "app.services.collectors.weather_collector.get_radar_client",
                return_value=client,
            ),
        ):
            assert await collector._get_precipitation(us_location) is None


class TestKurokkuPrecipitationFormat:
    def test_wet_produces_a_key(self, us_location):
        transform = KurokuuFormatTransform()
        entries = transform.format_precipitation(us_location, True)

        assert entries == [
            ("kurokku:weather:minneapolis:precip", "Rain", transform.temp_ttl)
        ]

    def test_dry_produces_a_key(self, us_location):
        entries = KurokuuFormatTransform().format_precipitation(us_location, False)

        assert entries[0][1] == "Dry"

    def test_unknown_produces_nothing(self, us_location):
        """None must not overwrite the existing key with a guess."""
        assert KurokuuFormatTransform().format_precipitation(us_location, None) == []

    def test_location_without_slug_is_skipped(self):
        location = Location(
            name="No Slug", latitude=44.98, longitude=-93.27, country_code="US"
        )
        assert KurokuuFormatTransform().format_precipitation(location, True) == []


class TestOutputManagerForwarding:
    async def test_precipitation_reaches_the_backend(self, us_location):
        manager = OutputManager()
        backend = MagicMock()
        backend.write = AsyncMock(
            return_value=MagicMock(success=True, keys_written=1, errors=[])
        )
        backend.close = AsyncMock()
        config = MagicMock(name="cfg", backend_type="redis")
        config.name = "test-backend"

        with patch(
            "app.services.outputs.manager._create_backend", return_value=backend
        ):
            await manager._write_single_backend(config, us_location, None, [], True)

        backend.write.assert_awaited_once_with(us_location, None, [], True)

    async def test_defaults_to_unknown_when_not_supplied(self, us_location):
        """Existing callers that omit the argument still work."""
        manager = OutputManager()
        backend = MagicMock()
        backend.write = AsyncMock(
            return_value=MagicMock(success=True, keys_written=1, errors=[])
        )
        backend.close = AsyncMock()
        config = MagicMock(backend_type="redis")
        config.name = "test-backend"

        with patch(
            "app.services.outputs.manager._create_backend", return_value=backend
        ):
            await manager._write_single_backend(config, us_location, None, [])

        backend.write.assert_awaited_once_with(us_location, None, [], None)
