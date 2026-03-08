"""
Unit tests for the Kurokku format transform.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.outputs.formats.kurokku import KurokuuFormatTransform
from app.services.weather_apis.base import WeatherAlert, WeatherData


def _make_location(slug="spring_hill", name="Spring Hill"):
    """Create a mock location."""
    loc = MagicMock()
    loc.slug = slug
    loc.name = name
    return loc


def _make_weather(temp_f=44.0, temp_c=6.7, humidity=65, condition_text="Clear"):
    """Create a WeatherData instance."""
    return WeatherData(
        temperature=temp_c,
        temperature_fahrenheit=temp_f,
        timestamp=datetime.now(UTC),
        condition_text=condition_text,
        humidity=humidity,
    )


def _make_alert(event="Severe Thunderstorm Warning", hours_until_expiry=2):
    """Create a WeatherAlert instance."""
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
class TestFormatTemperatureForDisplay:
    """Tests for temperature display formatting."""

    def test_normal_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(44.0) == "44°F"

    def test_zero_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(0.0) == "0°F"

    def test_negative_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(-5.3) == "-5°F"

    def test_rounds_to_integer(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(72.6) == "73°F"
        assert t.format_temperature_for_display(72.4) == "72°F"

    def test_none_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(None) == "--°F"

    def test_extremely_low_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(-100.0) == "LO°F"

    def test_extremely_high_temperature(self):
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(1000.0) == "HI°F"

    def test_boundary_low(self):
        """-99 should display normally."""
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(-99.0) == "-99°F"

    def test_boundary_high(self):
        """999 should display normally."""
        t = KurokuuFormatTransform()
        assert t.format_temperature_for_display(999.0) == "999°F"


@pytest.mark.unit
class TestFormatTemperature:
    """Tests for temperature key/value/ttl generation."""

    def test_produces_correct_key(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="spring_hill")
        weather = _make_weather(temp_f=44.0)

        entries = t.format_temperature(location, weather)
        assert len(entries) == 1
        key, value, ttl = entries[0]
        assert key == "kurokku:weather:spring_hill:temp"
        assert value == "44°F"
        assert ttl == 3600

    def test_none_weather_data(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        entries = t.format_temperature(location, None)
        assert len(entries) == 1
        assert entries[0][1] == "--°F"

    def test_no_slug_returns_empty(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug=None)
        entries = t.format_temperature(location, _make_weather())
        assert entries == []

    def test_custom_ttl(self):
        t = KurokuuFormatTransform({"temp_ttl": 1800})
        location = _make_location()
        entries = t.format_temperature(location, _make_weather())
        assert entries[0][2] == 1800


@pytest.mark.unit
class TestFormatHumidity:
    """Tests for humidity key/value/ttl generation."""

    def test_produces_correct_key(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="spring_hill")
        weather = _make_weather(humidity=65)

        entries = t.format_humidity(location, weather)
        assert len(entries) == 1
        key, value, ttl = entries[0]
        assert key == "kurokku:weather:spring_hill:humidity"
        assert value == "65%"
        assert ttl == 3600

    def test_none_weather_data(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        entries = t.format_humidity(location, None)
        assert len(entries) == 1
        assert entries[0][1] == "--%"

    def test_none_humidity(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        weather = _make_weather(humidity=None)
        entries = t.format_humidity(location, weather)
        assert entries[0][1] == "--%"

    def test_zero_humidity(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        weather = _make_weather(humidity=0)
        entries = t.format_humidity(location, weather)
        assert entries[0][1] == "0%"

    def test_no_slug_returns_empty(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug=None)
        entries = t.format_humidity(location, _make_weather())
        assert entries == []

    def test_custom_ttl(self):
        t = KurokuuFormatTransform({"temp_ttl": 1800})
        location = _make_location()
        entries = t.format_humidity(location, _make_weather())
        assert entries[0][2] == 1800


@pytest.mark.unit
class TestFormatConditions:
    """Tests for conditions key/value/ttl generation."""

    def test_produces_correct_key(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="spring_hill")
        weather = _make_weather(condition_text="Partly Cloudy")

        entries = t.format_conditions(location, weather)
        assert len(entries) == 1
        key, value, ttl = entries[0]
        assert key == "kurokku:weather:spring_hill:conditions"
        assert value == "Partly Cloudy"
        assert ttl == 3600

    def test_none_weather_data(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        entries = t.format_conditions(location, None)
        assert len(entries) == 1
        assert entries[0][1] == "--"

    def test_empty_condition_text(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        weather = _make_weather(condition_text="")
        entries = t.format_conditions(location, weather)
        assert entries[0][1] == "--"

    def test_no_slug_returns_empty(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug=None)
        entries = t.format_conditions(location, _make_weather())
        assert entries == []

    def test_custom_ttl(self):
        t = KurokuuFormatTransform({"temp_ttl": 1800})
        location = _make_location()
        entries = t.format_conditions(location, _make_weather())
        assert entries[0][2] == 1800


@pytest.mark.unit
class TestAlertPriority:
    """Tests for alert priority matching."""

    def test_tornado_highest_priority(self):
        t = KurokuuFormatTransform()
        assert t._get_alert_priority("Tornado Warning") == 0

    def test_severe_thunderstorm(self):
        t = KurokuuFormatTransform()
        assert t._get_alert_priority("Severe Thunderstorm Warning") == 1

    def test_case_insensitive(self):
        t = KurokuuFormatTransform()
        assert t._get_alert_priority("TORNADO WARNING") == 0
        assert t._get_alert_priority("tornado warning") == 0

    def test_partial_match(self):
        t = KurokuuFormatTransform()
        assert t._get_alert_priority("Flash Flood Warning") == 1
        assert t._get_alert_priority("High Wind Warning") == 2

    def test_unknown_event_gets_low_priority(self):
        t = KurokuuFormatTransform()
        assert t._get_alert_priority("Unknown Weather Event") == 5

    def test_custom_priorities(self):
        custom = {"test event": 0, "other event": 3}
        t = KurokuuFormatTransform({"alert_priorities": custom})
        assert t._get_alert_priority("Test Event Warning") == 0
        assert t._get_alert_priority("Other Event") == 3
        assert t._get_alert_priority("Tornado Warning") == 5  # Not in custom


@pytest.mark.unit
class TestDisplayDuration:
    """Tests for display duration calculation."""

    def test_short_message(self):
        t = KurokuuFormatTransform()
        # "Frost" = 5 chars -> 5 * 0.3 + 3.0 = 4.5
        assert t._calculate_display_duration("Frost") == "4.5s"

    def test_longer_message(self):
        t = KurokuuFormatTransform()
        msg = "Severe Thunderstorm Warning"
        expected = f"{round(len(msg) * 0.3 + 3.0, 1)}s"
        assert t._calculate_display_duration(msg) == expected

    def test_empty_message(self):
        t = KurokuuFormatTransform()
        assert t._calculate_display_duration("") == "3.0s"


@pytest.mark.unit
class TestFormatAlerts:
    """Tests for alert key/value/ttl generation."""

    def test_produces_delete_pattern(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="spring_hill")
        alerts = [_make_alert()]

        delete_patterns, _entries = t.format_alerts(location, alerts)
        assert delete_patterns == ["kurokku:alert:weather:spring_hill:*"]

    def test_alert_key_format(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="spring_hill")
        alerts = [_make_alert()]

        _, entries = t.format_alerts(location, alerts)
        assert len(entries) == 1
        key, _value, ttl = entries[0]
        assert key == "kurokku:alert:weather:spring_hill:0"
        assert ttl > 0

    def test_alert_value_format(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        alerts = [_make_alert(event="Tornado Warning")]

        _, entries = t.format_alerts(location, alerts)
        data = json.loads(entries[0][1])

        assert data["message"] == "Tornado Warning"
        assert data["priority"] == 0
        assert data["delete_after_display"] is False
        assert "timestamp" in data
        assert data["display_duration"].endswith("s")

    def test_multiple_alerts_indexed(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug="test")
        alerts = [
            _make_alert(event="Tornado Warning"),
            _make_alert(event="Flood Warning"),
        ]

        _, entries = t.format_alerts(location, alerts)
        assert len(entries) == 2
        assert entries[0][0] == "kurokku:alert:weather:test:0"
        assert entries[1][0] == "kurokku:alert:weather:test:1"

    def test_expired_alerts_skipped(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        alerts = [_make_alert(hours_until_expiry=-1)]  # Already expired

        _, entries = t.format_alerts(location, alerts)
        assert entries == []

    def test_no_slug_returns_empty(self):
        t = KurokuuFormatTransform()
        location = _make_location(slug=None)
        alerts = [_make_alert()]

        delete_patterns, entries = t.format_alerts(location, alerts)
        assert delete_patterns == []
        assert entries == []

    def test_empty_alerts(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        delete_patterns, entries = t.format_alerts(location, [])
        assert delete_patterns == ["kurokku:alert:weather:spring_hill:*"]
        assert entries == []

    def test_alert_ttl_from_expiration(self):
        t = KurokuuFormatTransform()
        location = _make_location()
        alert = _make_alert(hours_until_expiry=1)
        _, entries = t.format_alerts(location, [alert])

        _, _, ttl = entries[0]
        # Should be approximately 3600 seconds (1 hour)
        assert 3500 < ttl <= 3600

    def test_malformed_alert_skipped_others_preserved(self):
        """A bad alert shouldn't prevent valid alerts from being formatted."""
        t = KurokuuFormatTransform()
        location = _make_location(slug="test")

        good_alert = _make_alert(event="Tornado Warning")
        bad_alert = MagicMock()
        bad_alert.expires = None  # Will cause an exception in TTL calculation
        good_alert_2 = _make_alert(event="Flood Warning")

        _, entries = t.format_alerts(location, [good_alert, bad_alert, good_alert_2])
        assert len(entries) == 2
        data_0 = json.loads(entries[0][1])
        data_1 = json.loads(entries[1][1])
        assert data_0["message"] == "Tornado Warning"
        assert data_1["message"] == "Flood Warning"
