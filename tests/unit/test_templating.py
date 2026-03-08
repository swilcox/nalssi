"""Tests for the templating module."""

from app.templating import weather_icon


class TestWeatherIcon:
    """Tests for the weather_icon filter."""

    def test_clear_conditions(self):
        assert weather_icon("Clear sky") == "clear"
        assert weather_icon("Sunny") == "clear"
        assert weather_icon("Fair") == "clear"

    def test_cloudy_conditions(self):
        assert weather_icon("Partly Cloudy") == "partly-cloudy"
        assert weather_icon("Overcast") == "cloudy"
        assert weather_icon("Mainly clear") == "partly-cloudy"
        assert weather_icon("scattered clouds") == "partly-cloudy"

    def test_rain_conditions(self):
        assert weather_icon("Slight rain") == "rain-light"
        assert weather_icon("Moderate rain") == "rain"
        assert weather_icon("Heavy rain") == "rain-heavy"
        assert weather_icon("Light drizzle") == "rain-light"
        assert weather_icon("Moderate rain showers") == "rain"

    def test_snow_conditions(self):
        assert weather_icon("Slight snowfall") == "snow"
        assert weather_icon("Heavy snowfall") == "snow-heavy"
        assert weather_icon("Snow grains") == "snow"
        assert weather_icon("Light freezing rain") == "sleet"

    def test_thunderstorm(self):
        assert weather_icon("Thunderstorm") == "thunderstorm"
        assert weather_icon("Thunderstorm with slight hail") == "thunderstorm"

    def test_fog(self):
        assert weather_icon("Fog") == "fog"
        assert weather_icon("Depositing rime fog") == "fog"
        assert weather_icon("mist") == "fog"

    def test_unknown(self):
        assert weather_icon(None) == "unknown"
        assert weather_icon("") == "unknown"
        assert weather_icon("Something weird") == "unknown"

    def test_case_insensitive(self):
        assert weather_icon("CLEAR SKY") == "clear"
        assert weather_icon("heavy RAIN") == "rain-heavy"
