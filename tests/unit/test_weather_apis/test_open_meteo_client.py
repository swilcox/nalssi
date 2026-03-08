"""
Unit tests for Open-Meteo Weather API client.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.services.weather_apis.open_meteo import (
    WMO_WEATHER_CODES,
    OpenMeteoClient,
)


@pytest.fixture
def open_meteo_responses():
    """Load Open-Meteo API response fixtures."""
    fixtures_path = (
        Path(__file__).parent.parent.parent / "fixtures" / "open_meteo_responses.json"
    )
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def open_meteo_client():
    """Create an Open-Meteo client instance."""
    return OpenMeteoClient()


@pytest.mark.unit
def test_open_meteo_client_initialization(open_meteo_client):
    """Test that Open-Meteo client initializes correctly."""
    assert open_meteo_client is not None
    assert open_meteo_client.base_url == "https://api.open-meteo.com/v1"
    assert open_meteo_client.name == "open-meteo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_current_weather_success(
    open_meteo_client, open_meteo_responses, respx_mock
):
    """Test successful current weather retrieval from Open-Meteo."""
    lat, lon = 51.5074, -0.1278

    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200, json=open_meteo_responses["forecast_response"]
        )
    )

    weather = await open_meteo_client.get_current_weather(lat, lon)

    assert weather is not None
    assert weather.temperature == 8.3
    assert weather.humidity == 78
    assert weather.wind_speed == 4.2
    assert weather.wind_direction == 210
    assert weather.wind_gust == 7.8
    assert weather.feels_like == 5.1
    assert weather.cloud_cover == 85
    assert weather.precipitation == 0.2
    assert weather.pressure == 1005.4
    assert weather.condition_code == "61"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_current_weather_field_mapping(
    open_meteo_client, open_meteo_responses, respx_mock
):
    """Test that Open-Meteo fields are mapped correctly."""
    lat, lon = 51.5074, -0.1278

    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(
            200, json=open_meteo_responses["forecast_response"]
        )
    )

    weather = await open_meteo_client.get_current_weather(lat, lon)

    # Temperature conversion: 8.3°C → Fahrenheit
    assert weather.temperature == 8.3
    assert weather.temperature_fahrenheit == pytest.approx(46.94, rel=0.01)

    # Weather code 61 → "Slight rain"
    assert weather.condition_text == "Slight rain"

    # Raw data should be preserved
    assert weather.raw_data is not None
    assert "current" in weather.raw_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_current_weather_invalid_coordinates(open_meteo_client):
    """Test that invalid coordinates raise ValueError."""
    with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
        await open_meteo_client.get_current_weather(100.0, 0.0)

    with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
        await open_meteo_client.get_current_weather(0.0, 200.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_current_weather_api_error(
    open_meteo_client, respx_mock
):
    """Test handling of API errors."""
    lat, lon = 51.5074, -0.1278

    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(httpx.HTTPStatusError):
        await open_meteo_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_current_weather_timeout(
    open_meteo_client, respx_mock
):
    """Test handling of timeouts."""
    lat, lon = 51.5074, -0.1278

    respx_mock.get("https://api.open-meteo.com/v1/forecast").mock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    with pytest.raises(httpx.TimeoutException):
        await open_meteo_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_meteo_get_alerts_returns_empty(open_meteo_client):
    """Test that get_alerts returns empty list (not supported)."""
    alerts = await open_meteo_client.get_alerts(51.5074, -0.1278)
    assert alerts == []


@pytest.mark.unit
def test_open_meteo_client_str_representation(open_meteo_client):
    """Test string representation of Open-Meteo client."""
    str_repr = str(open_meteo_client)
    assert "OpenMeteo" in str_repr or "open-meteo" in str_repr


@pytest.mark.unit
def test_wmo_weather_codes_has_common_codes():
    """Test that WMO code lookup contains expected entries."""
    assert WMO_WEATHER_CODES[0] == "Clear sky"
    assert WMO_WEATHER_CODES[3] == "Overcast"
    assert WMO_WEATHER_CODES[61] == "Slight rain"
    assert WMO_WEATHER_CODES[95] == "Thunderstorm"
