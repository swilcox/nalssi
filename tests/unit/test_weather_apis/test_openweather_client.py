"""
Unit tests for OpenWeatherMap API client.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.services.weather_apis.openweather import OpenWeatherClient


@pytest.fixture
def openweather_responses():
    """Load OpenWeatherMap API response fixtures."""
    fixtures_path = (
        Path(__file__).parent.parent.parent / "fixtures" / "openweather_responses.json"
    )
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def openweather_client():
    """Create an OpenWeather client instance."""
    return OpenWeatherClient()


@pytest.mark.unit
def test_openweather_client_initialization(openweather_client):
    """Test that OpenWeather client initializes correctly."""
    assert openweather_client is not None
    assert openweather_client.base_url == "https://api.openweathermap.org/data/2.5"
    assert openweather_client.name == "openweather"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_success(
    openweather_client, openweather_responses, respx_mock
):
    """Test successful current weather retrieval from OpenWeatherMap."""
    lat, lon = 35.6895, 139.6917

    respx_mock.get("https://api.openweathermap.org/data/2.5/weather").mock(
        return_value=httpx.Response(
            200, json=openweather_responses["weather_response"]
        )
    )

    weather = await openweather_client.get_current_weather(lat, lon)

    assert weather is not None
    assert weather.temperature == 12.5
    assert weather.humidity == 55
    assert weather.wind_speed == 3.6
    assert weather.wind_direction == 160
    assert weather.wind_gust == 6.2
    assert weather.feels_like == 10.8
    assert weather.cloud_cover == 40
    assert weather.precipitation == 0.5
    assert weather.pressure == 1018
    assert weather.visibility == 10000
    assert weather.condition_text == "scattered clouds"
    assert weather.condition_code == "802"
    assert weather.icon == "03d"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_field_mapping(
    openweather_client, openweather_responses, respx_mock
):
    """Test that OpenWeather fields are mapped correctly."""
    lat, lon = 35.6895, 139.6917

    respx_mock.get("https://api.openweathermap.org/data/2.5/weather").mock(
        return_value=httpx.Response(
            200, json=openweather_responses["weather_response"]
        )
    )

    weather = await openweather_client.get_current_weather(lat, lon)

    # Temperature conversion: 12.5°C → Fahrenheit
    assert weather.temperature == 12.5
    assert weather.temperature_fahrenheit == pytest.approx(54.5, rel=0.01)

    # Raw data should be preserved
    assert weather.raw_data is not None
    assert weather.raw_data["name"] == "Tokyo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_missing_optional_fields(
    openweather_client, openweather_responses, respx_mock
):
    """Test handling when optional fields (rain, gust) are missing."""
    lat, lon = 40.4168, -3.7038

    respx_mock.get("https://api.openweathermap.org/data/2.5/weather").mock(
        return_value=httpx.Response(
            200, json=openweather_responses["weather_response_no_rain_no_gust"]
        )
    )

    weather = await openweather_client.get_current_weather(lat, lon)

    assert weather is not None
    assert weather.temperature == 22.0
    assert weather.precipitation is None
    assert weather.wind_gust is None
    assert weather.wind_speed == 2.1
    assert weather.condition_text == "clear sky"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_invalid_coordinates(openweather_client):
    """Test that invalid coordinates raise ValueError."""
    with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
        await openweather_client.get_current_weather(100.0, 0.0)

    with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
        await openweather_client.get_current_weather(0.0, 200.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_api_error(
    openweather_client, respx_mock
):
    """Test handling of API errors."""
    lat, lon = 35.6895, 139.6917

    respx_mock.get("https://api.openweathermap.org/data/2.5/weather").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(httpx.HTTPStatusError):
        await openweather_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_current_weather_timeout(
    openweather_client, respx_mock
):
    """Test handling of timeouts."""
    lat, lon = 35.6895, 139.6917

    respx_mock.get("https://api.openweathermap.org/data/2.5/weather").mock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    with pytest.raises(httpx.TimeoutException):
        await openweather_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openweather_get_alerts_returns_empty(openweather_client):
    """Test that get_alerts returns empty list (not supported in free tier)."""
    alerts = await openweather_client.get_alerts(35.6895, 139.6917)
    assert alerts == []


@pytest.mark.unit
def test_openweather_client_str_representation(openweather_client):
    """Test string representation of OpenWeather client."""
    str_repr = str(openweather_client)
    assert "OpenWeather" in str_repr or "openweather" in str_repr
