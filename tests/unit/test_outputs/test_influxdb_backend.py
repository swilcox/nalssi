"""
Unit tests for InfluxDB output backend.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.outputs.influxdb_backend import InfluxDBOutputBackend
from app.services.weather_apis.base import WeatherAlert, WeatherData


def _make_location(slug="spring_hill", name="Spring Hill", country_code="US"):
    loc = MagicMock()
    loc.slug = slug
    loc.name = name
    loc.country_code = country_code
    return loc


def _make_weather(temp_c=18.5, temp_f=65.3, humidity=65, **kwargs):
    defaults = {
        "temperature": temp_c,
        "temperature_fahrenheit": temp_f,
        "timestamp": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        "condition_text": "Partly Cloudy",
        "humidity": humidity,
        "pressure": 1013.25,
        "wind_speed": 5.5,
        "wind_direction": 270,
    }
    defaults.update(kwargs)
    return WeatherData(**defaults)


def _make_alert(event="Severe Thunderstorm Warning", severity="Severe"):
    now = datetime.now(UTC)
    return WeatherAlert(
        event=event,
        headline=f"{event} issued",
        description="Test alert description",
        severity=severity,
        urgency="Immediate",
        effective=now - timedelta(hours=1),
        expires=now + timedelta(hours=2),
        areas=["Test County", "Other County"],
    )


def _make_backend(config=None):
    """Create backend with mocked InfluxDB client."""
    backend = InfluxDBOutputBackend(
        name="test-influxdb",
        config=config or {},
    )
    mock_client = MagicMock()
    mock_write_api = MagicMock()
    mock_write_api.write = AsyncMock()
    # write_api() is a sync method that returns the write API object
    mock_client.write_api.return_value = mock_write_api
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.close = AsyncMock()
    backend._client = mock_client
    return backend, mock_client, mock_write_api


@pytest.mark.unit
class TestInfluxDBOutputBackend:
    """Tests for InfluxDBOutputBackend."""

    def test_config_defaults_to_settings(self):
        """Backend should use settings values when config keys are missing."""
        backend = InfluxDBOutputBackend(name="test", config={})
        assert backend._bucket == "weather"  # from settings default

    def test_config_overrides_settings(self):
        """Config values should override settings defaults."""
        backend = InfluxDBOutputBackend(
            name="test",
            config={
                "url": "http://custom:8086",
                "token": "my-token",
                "org": "my-org",
                "bucket": "my-bucket",
            },
        )
        assert backend._url == "http://custom:8086"
        assert backend._token == "my-token"
        assert backend._org == "my-org"
        assert backend._bucket == "my-bucket"

    def test_accepts_format_params(self):
        """Backend should accept format_type/format_config without error."""
        backend = InfluxDBOutputBackend(
            name="test",
            config={},
            format_type="some_format",
            format_config={"key": "value"},
        )
        assert backend is not None

    @pytest.mark.asyncio
    async def test_write_weather_data(self):
        """Should write a weather point with correct tags and fields."""
        backend, mock_client, mock_write_api = _make_backend()
        location = _make_location()
        weather = _make_weather()

        result = await backend.write(location, weather, [])

        assert result.success is True
        assert result.keys_written == 1
        assert result.backend_name == "test-influxdb"

        # Verify write was called
        mock_write_api.write.assert_called_once()
        call_kwargs = mock_write_api.write.call_args
        points = call_kwargs.kwargs.get("record") or call_kwargs[1].get("record")
        assert len(points) == 1

        # Inspect the point's line protocol
        line = points[0].to_line_protocol()
        assert "weather," in line or line.startswith("weather ")
        assert "location=spring_hill" in line
        assert "country=US" in line
        assert "temperature=18.5" in line
        assert "temperature_fahrenheit=65.3" in line
        assert "humidity=65i" in line
        assert "pressure=1013.25" in line
        assert 'condition="Partly Cloudy"' in line

    @pytest.mark.asyncio
    async def test_write_weather_skips_none_fields(self):
        """Fields with None values should not appear in the point."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location()
        weather = _make_weather(humidity=None, pressure=None)

        result = await backend.write(location, weather, [])

        assert result.success is True
        points = mock_write_api.write.call_args.kwargs.get(
            "record"
        ) or mock_write_api.write.call_args[1].get("record")
        line = points[0].to_line_protocol()
        assert "humidity=" not in line
        assert "pressure=" not in line
        # Fields that were set should still be present
        assert "temperature=18.5" in line

    @pytest.mark.asyncio
    async def test_write_alerts(self):
        """Each alert should become a separate weather_alert point."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location()
        alerts = [
            _make_alert(event="Tornado Warning", severity="Extreme"),
            _make_alert(event="Flood Watch", severity="Moderate"),
        ]

        result = await backend.write(location, None, alerts)

        assert result.success is True
        assert result.keys_written == 2
        points = mock_write_api.write.call_args.kwargs.get(
            "record"
        ) or mock_write_api.write.call_args[1].get("record")
        assert len(points) == 2

        line0 = points[0].to_line_protocol()
        assert "weather_alert," in line0 or line0.startswith("weather_alert ")
        assert "severity=extreme" in line0
        assert "event=Tornado\\ Warning" in line0
        assert 'headline="Tornado Warning issued"' in line0
        assert 'areas="Test County, Other County"' in line0
        assert "active=1i" in line0

        line1 = points[1].to_line_protocol()
        assert "severity=moderate" in line1

    @pytest.mark.asyncio
    async def test_write_weather_and_alerts(self):
        """Writing both weather and alerts should produce correct point count."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location()
        weather = _make_weather()
        alerts = [_make_alert()]

        result = await backend.write(location, weather, alerts)

        assert result.success is True
        assert result.keys_written == 2  # 1 weather + 1 alert

    @pytest.mark.asyncio
    async def test_write_no_data(self):
        """No weather and no alerts should write zero points."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location()

        result = await backend.write(location, None, [])

        assert result.success is True
        assert result.keys_written == 0
        mock_write_api.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_write_handles_influxdb_error(self):
        """InfluxDB write errors should be caught and returned."""
        backend, _, mock_write_api = _make_backend()
        mock_write_api.write.side_effect = Exception("Connection refused")
        location = _make_location()

        result = await backend.write(location, _make_weather(), [])

        assert result.success is False
        assert "Connection refused" in result.errors[0]

    @pytest.mark.asyncio
    async def test_write_uses_configured_bucket(self):
        """Write should use the bucket from config."""
        backend, _, mock_write_api = _make_backend(config={"bucket": "custom-bucket"})
        location = _make_location()

        await backend.write(location, _make_weather(), [])

        call_kwargs = mock_write_api.write.call_args
        bucket = call_kwargs.kwargs.get("bucket") or call_kwargs[1].get("bucket")
        assert bucket == "custom-bucket"

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        """Successful ping should return True."""
        backend, mock_client, _ = _make_backend()
        mock_client.ping.return_value = True

        assert await backend.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self):
        """Failed ping should return False."""
        backend, mock_client, _ = _make_backend()
        mock_client.ping.side_effect = Exception("Connection refused")

        assert await backend.test_connection() is False

    @pytest.mark.asyncio
    async def test_close(self):
        """Close should close the client and reset to None."""
        backend, mock_client, _ = _make_backend()

        await backend.close()

        mock_client.close.assert_called_once()
        assert backend._client is None

    @pytest.mark.asyncio
    async def test_close_when_no_client(self):
        """Close with no initialized client should be a no-op."""
        backend = InfluxDBOutputBackend(name="test", config={})
        await backend.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_weather_source_tag(self):
        """Source tag should be added when raw_data has source."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location()
        weather = _make_weather(raw_data={"source": "noaa"})

        await backend.write(location, weather, [])

        points = mock_write_api.write.call_args.kwargs.get(
            "record"
        ) or mock_write_api.write.call_args[1].get("record")
        line = points[0].to_line_protocol()
        assert "source=noaa" in line

    @pytest.mark.asyncio
    async def test_location_falls_back_to_name(self):
        """When slug is None, location tag should use name."""
        backend, _, mock_write_api = _make_backend()
        location = _make_location(slug=None, name="My City")

        await backend.write(location, _make_weather(), [])

        points = mock_write_api.write.call_args.kwargs.get(
            "record"
        ) or mock_write_api.write.call_args[1].get("record")
        line = points[0].to_line_protocol()
        assert "location=My\\ City" in line

    def test_lazy_client_creation(self):
        """Client should be created lazily on first _get_client call."""
        backend = InfluxDBOutputBackend(
            name="test",
            config={"url": "http://localhost:8086", "token": "t", "org": "o"},
        )
        assert backend._client is None

        with patch(
            "app.services.outputs.influxdb_backend.InfluxDBClientAsync"
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            client = backend._get_client()
            mock_cls.assert_called_once_with(
                url="http://localhost:8086",
                token="t",
                org="o",
                timeout=10_000,
            )
            # Second call should reuse
            client2 = backend._get_client()
            assert client is client2
            assert mock_cls.call_count == 1
