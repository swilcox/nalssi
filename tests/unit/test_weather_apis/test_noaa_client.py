"""
Unit tests for NOAA Weather API client.

Following TDD: Write tests first, then implement.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.services.weather_apis.noaa import NOAAWeatherClient


@pytest.fixture
def noaa_responses():
    """Load NOAA API response fixtures."""
    fixtures_path = (
        Path(__file__).parent.parent.parent / "fixtures" / "noaa_responses.json"
    )
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def noaa_client():
    """Create a NOAA client instance."""
    return NOAAWeatherClient()


@pytest.mark.unit
def test_noaa_client_initialization(noaa_client):
    """Test that NOAA client initializes correctly."""
    assert noaa_client is not None
    assert noaa_client.base_url == "https://api.weather.gov"
    assert noaa_client.name == "noaa"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_current_weather_success(
    noaa_client, noaa_responses, respx_mock
):
    """Test successful current weather retrieval from NOAA."""
    lat, lon = 37.7749, -122.4194

    # Mock the points endpoint
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )

    # Mock the stations endpoint
    respx_mock.get("https://api.weather.gov/gridpoints/MTR/90,112/stations").mock(
        return_value=httpx.Response(200, json=noaa_responses["stations_response"])
    )

    # Mock the observation endpoint
    respx_mock.get("https://api.weather.gov/stations/KSFO/observations/latest").mock(
        return_value=httpx.Response(200, json=noaa_responses["observation_response"])
    )

    weather = await noaa_client.get_current_weather(lat, lon)

    assert weather is not None
    assert weather.temperature == 18.5
    assert weather.humidity == 65
    assert weather.wind_speed == 5.5
    assert weather.wind_direction == 270
    assert weather.condition_text == "Partly Cloudy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_current_weather_converts_units(
    noaa_client, noaa_responses, respx_mock
):
    """Test that NOAA client converts units correctly."""
    lat, lon = 37.7749, -122.4194

    # Mock all required endpoints
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )
    respx_mock.get("https://api.weather.gov/gridpoints/MTR/90,112/stations").mock(
        return_value=httpx.Response(200, json=noaa_responses["stations_response"])
    )
    respx_mock.get("https://api.weather.gov/stations/KSFO/observations/latest").mock(
        return_value=httpx.Response(200, json=noaa_responses["observation_response"])
    )

    weather = await noaa_client.get_current_weather(lat, lon)

    # Temperature should be in Celsius (18.5°C)
    assert weather.temperature == 18.5
    # Should also provide Fahrenheit conversion (18.5°C = 65.3°F)
    assert weather.temperature_fahrenheit == pytest.approx(65.3, rel=0.1)
    # Pressure should be converted from Pa to hPa (101325 Pa = 1013.25 hPa)
    assert weather.pressure == pytest.approx(1013.25, rel=0.01)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_current_weather_invalid_coordinates(noaa_client):
    """Test that invalid coordinates raise ValueError."""
    # Latitude out of range
    with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
        await noaa_client.get_current_weather(100.0, 0.0)

    # Longitude out of range
    with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
        await noaa_client.get_current_weather(0.0, 200.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_current_weather_api_error(noaa_client, respx_mock):
    """Test handling of API errors."""
    lat, lon = 37.7749, -122.4194

    # Mock API error response
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(Exception):  # Should raise an API error
        await noaa_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_current_weather_timeout(noaa_client, respx_mock):
    """Test handling of timeouts."""
    lat, lon = 37.7749, -122.4194

    # Mock timeout
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    with pytest.raises(httpx.TimeoutException):
        await noaa_client.get_current_weather(lat, lon)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_alerts(noaa_client, noaa_responses, respx_mock):
    """Test retrieving weather alerts from NOAA."""
    lat, lon = 37.7749, -122.4194

    # Mock the points endpoint to get the zone
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )

    # Mock the alerts endpoint
    respx_mock.get("https://api.weather.gov/alerts/active").mock(
        return_value=httpx.Response(200, json=noaa_responses["alerts_response"])
    )

    alerts = await noaa_client.get_alerts(lat, lon)

    assert alerts is not None
    assert len(alerts) > 0

    alert = alerts[0]
    assert alert.event == "High Wind Warning"
    assert alert.severity == "Severe"
    assert alert.urgency == "Immediate"
    assert alert.certainty == "Likely"
    assert alert.category == "Met"
    assert alert.response_type == "Prepare"
    assert alert.sender_name == "NWS San Francisco CA"
    assert alert.status == "Actual"
    assert alert.message_type == "Alert"
    assert alert.onset is not None
    assert alert.ends is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_alerts_no_active_alerts(
    noaa_client, noaa_responses, respx_mock
):
    """Test handling when there are no active alerts."""
    lat, lon = 37.7749, -122.4194

    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )

    # Mock empty alerts response
    respx_mock.get("https://api.weather.gov/alerts/active").mock(
        return_value=httpx.Response(200, json={"features": []})
    )

    alerts = await noaa_client.get_alerts(lat, lon)

    assert alerts == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_client_sets_user_agent(noaa_client, respx_mock):
    """Test that client sets proper User-Agent header."""
    lat, lon = 37.7749, -122.4194

    # Capture the request
    route = respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}")
    route.mock(return_value=httpx.Response(404))  # We just want to check headers

    try:
        await noaa_client.get_current_weather(lat, lon)
    except Exception:
        pass  # We expect this to fail, we just want to check the request

    # Verify User-Agent was set
    assert route.called
    request = route.calls.last.request
    assert "User-Agent" in request.headers
    assert "nalssi" in request.headers["User-Agent"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_forecast(noaa_client, noaa_responses, respx_mock):
    """Test retrieving forecast periods from NOAA."""
    lat, lon = 37.7749, -122.4194

    # Mock the points endpoint
    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )

    # Mock the forecast endpoint
    respx_mock.get(
        "https://api.weather.gov/gridpoints/MTR/90,112/forecast"
    ).mock(
        return_value=httpx.Response(200, json=noaa_responses["forecast_response"])
    )

    periods = await noaa_client.get_forecast(lat, lon)

    assert len(periods) == 3

    # First period: daytime
    day = periods[0]
    assert day.is_daytime is True
    assert day.condition_text == "Partly Cloudy"
    assert day.precipitation_probability == 20
    assert day.start_time is not None
    assert day.end_time is not None
    assert day.detailed_forecast is not None
    assert "62" in day.detailed_forecast

    # Temperature: 62°F should convert to ~16.7°C
    assert day.temperature == pytest.approx(16.67, abs=0.1)
    assert day.temperature_fahrenheit == pytest.approx(62.0)

    # Wind: "5 to 10 mph" -> take max (10 mph) -> ~4.5 m/s
    assert day.wind_speed is not None
    assert day.wind_speed == pytest.approx(4.5, abs=0.1)

    # Wind direction: "NW" -> 315 degrees
    assert day.wind_direction == 315

    # Second period: nighttime
    night = periods[1]
    assert night.is_daytime is False
    assert night.condition_text == "Chance Rain"
    assert night.precipitation_probability == 60
    # 45°F -> ~7.2°C
    assert night.temperature == pytest.approx(7.22, abs=0.1)
    # Wind direction: "S" -> 180 degrees
    assert night.wind_direction == 180


@pytest.mark.unit
@pytest.mark.asyncio
async def test_noaa_get_forecast_empty(noaa_client, noaa_responses, respx_mock):
    """Test handling of empty forecast response."""
    lat, lon = 37.7749, -122.4194

    respx_mock.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json=noaa_responses["points_response"])
    )
    respx_mock.get(
        "https://api.weather.gov/gridpoints/MTR/90,112/forecast"
    ).mock(
        return_value=httpx.Response(
            200, json={"properties": {"periods": []}}
        )
    )

    periods = await noaa_client.get_forecast(lat, lon)
    assert periods == []


@pytest.mark.unit
def test_noaa_parse_wind_speed():
    """Test wind speed string parsing."""
    from app.services.weather_apis.noaa import NOAAWeatherClient

    parse = NOAAWeatherClient._parse_wind_speed

    # "5 to 10 mph" -> max is 10 mph -> ~4.5 m/s
    assert parse("5 to 10 mph") == pytest.approx(4.5, abs=0.1)
    # "10 mph" -> 10 mph -> ~4.5 m/s
    assert parse("10 mph") == pytest.approx(4.5, abs=0.1)
    # "15 to 20 mph" -> max is 20 mph -> ~8.9 m/s
    assert parse("15 to 20 mph") == pytest.approx(8.9, abs=0.1)
    # None
    assert parse(None) is None
    # Empty string
    assert parse("") is None


@pytest.mark.unit
def test_noaa_compass_to_degrees():
    """Test compass direction to degrees conversion."""
    from app.services.weather_apis.noaa import NOAAWeatherClient

    convert = NOAAWeatherClient._compass_to_degrees

    assert convert("N") == 0
    assert convert("NW") == 315
    assert convert("S") == 180
    assert convert("SSW") == 202
    assert convert("E") == 90
    assert convert(None) is None


@pytest.mark.unit
def test_noaa_client_str_representation(noaa_client):
    """Test string representation of NOAA client."""
    str_repr = str(noaa_client)
    assert "NOAA" in str_repr or "noaa" in str_repr
