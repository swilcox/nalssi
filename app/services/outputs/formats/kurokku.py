"""
Kurokku format transform for led-kurokku Redis integration.

Produces Redis keys/values in the exact format that led-kurokku expects.
"""

import hashlib
import json
from datetime import UTC, datetime

import structlog

from app.models.location import Location
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = structlog.get_logger()

# Default alert priority mapping (event substring -> priority level)
DEFAULT_ALERT_PRIORITIES = {
    "tornado": 0,
    "tsunami": 0,
    "extreme wind": 0,
    "hurricane": 0,
    "typhoon": 0,
    "storm surge": 0,
    "flash flood": 1,
    "severe thunderstorm": 1,
    "blizzard": 1,
    "ice storm": 2,
    "flood": 2,
    "winter storm": 2,
    "high wind": 2,
    # Heat Watch and Warning (both the legacy "excessive heat" naming and the
    # current "extreme heat" naming) collapse to the advisory tier (3): they
    # often last for days, so surfacing them at warning priority spams the
    # clock. The single keyword matches both the watch and warning event names
    # via longest-match lookup.
    "excessive heat": 3,
    "extreme heat": 3,
    "fire weather": 2,
    "tornado watch": 2,
    "tsunami watch": 3,
    "storm surge watch": 3,
    "hurricane watch": 3,
    "typhoon watch": 3,
    "severe thunderstorm watch": 3,
    "flash flood watch": 3,
    "flood watch": 3,
    "blizzard watch": 3,
    "ice storm watch": 3,
    "winter storm watch": 3,
    "high wind watch": 3,
    "fire weather watch": 3,
    "wind chill": 3,
    "freeze": 3,
    "frost": 3,
    "cold weather advisory": 3,
    "heat advisory": 3,
    "wind advisory": 3,
    "flood advisory": 3,
    "dense fog": 3,
    "winter weather": 4,
    "special weather": 4,
}

# CAP severity fallback mapping when no event keyword matches
CAP_SEVERITY_PRIORITIES = {
    "extreme": 1,
    "severe": 2,
    "moderate": 3,
    "minor": 4,
    "unknown": 5,
}


def _coerce_number(value, default, kind, field):
    """
    Coerce a config value to int or float, tolerating strings like "1.75s".

    Falls back to the default (and logs a warning) if the value can't be parsed.
    """
    if value is None:
        return kind(default)
    if isinstance(value, int | float):
        return kind(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("sS").strip()
        try:
            return kind(float(stripped))
        except ValueError:
            pass
    logger.warning(
        "Invalid kurokku format_config value for %s: %r, using default %r",
        field,
        value,
        default,
    )
    return kind(default)


class KurokuuFormatTransform:
    """
    Transforms weather data into the key/value format expected by led-kurokku.

    Redis key patterns:
        Temperature: kurokku:weather:{slug}:temp = "44°F"  (TTL 3600s)
        Alerts: kurokku:alert:weather:{slug}:{alert_hash} = JSON  (TTL from expiration)

    Alert key suffixes are a stable hash of the alert id so that diff-based
    sync can detect which alerts are new, changed, or gone without rewriting
    the full set every collection cycle.
    """

    DEFAULT_TEMP_TTL = 3600  # 1 hour
    DISPLAY_DURATION_BASE = 1.75  # seconds
    DISPLAY_DURATION_PER_CHAR = 0.3  # seconds per character

    def __init__(self, format_config: dict | None = None):
        """
        Initialize the transform.

        Args:
            format_config: Optional config dict with keys like:
                - alert_priorities: dict mapping event substrings to priority levels
                - temp_ttl: TTL for temperature keys (default 3600)
        """
        self.format_config = format_config or {}
        self.alert_priorities = {
            k.lower(): v
            for k, v in self.format_config.get(
                "alert_priorities", DEFAULT_ALERT_PRIORITIES
            ).items()
        }
        self.temp_ttl = _coerce_number(
            self.format_config.get("temp_ttl"), self.DEFAULT_TEMP_TTL, int, "temp_ttl"
        )
        self.display_duration_base = _coerce_number(
            self.format_config.get("display_duration_base"),
            self.DISPLAY_DURATION_BASE,
            float,
            "display_duration_base",
        )
        self.display_duration_per_char = _coerce_number(
            self.format_config.get("display_duration_per_char"),
            self.DISPLAY_DURATION_PER_CHAR,
            float,
            "display_duration_per_char",
        )

    def format_temperature_for_display(self, temp_f: float | None) -> str:
        """
        Format temperature for LED display.

        Args:
            temp_f: Temperature in Fahrenheit, or None

        Returns:
            Formatted string like "44°F", "LO°F", "HI°F", or "--°F"
        """
        if temp_f is None:
            return "--°F"
        if temp_f < -99:
            return "LO°F"
        if temp_f > 999:
            return "HI°F"
        return f"{round(temp_f)}°F"

    def format_temperature(
        self, location: Location, weather_data: WeatherData | None
    ) -> list[tuple[str, str, int]]:
        """
        Format temperature data into Redis key/value/ttl tuples.

        Args:
            location: Location model instance (must have slug)
            weather_data: Normalized weather data, or None

        Returns:
            List of (key, value, ttl) tuples
        """
        slug = location.slug
        if not slug:
            logger.warning(
                "Location %s has no slug, skipping temperature write",
                location.name,
            )
            return []

        temp_f = weather_data.temperature_fahrenheit if weather_data else None
        display_value = self.format_temperature_for_display(temp_f)
        key = f"kurokku:weather:{slug}:temp"

        return [(key, display_value, self.temp_ttl)]

    def format_humidity(
        self, location: Location, weather_data: WeatherData | None
    ) -> list[tuple[str, str, int]]:
        """
        Format humidity data into Redis key/value/ttl tuples.

        Args:
            location: Location model instance (must have slug)
            weather_data: Normalized weather data, or None

        Returns:
            List of (key, value, ttl) tuples
        """
        slug = location.slug
        if not slug:
            logger.warning(
                "Location %s has no slug, skipping humidity write",
                location.name,
            )
            return []

        humidity = weather_data.humidity if weather_data else None
        display_value = f"{humidity}%" if humidity is not None else "--%"
        key = f"kurokku:weather:{slug}:humidity"

        return [(key, display_value, self.temp_ttl)]

    def format_conditions(
        self, location: Location, weather_data: WeatherData | None
    ) -> list[tuple[str, str, int]]:
        """
        Format current conditions into Redis key/value/ttl tuples.

        Args:
            location: Location model instance (must have slug)
            weather_data: Normalized weather data, or None

        Returns:
            List of (key, value, ttl) tuples
        """
        slug = location.slug
        if not slug:
            logger.warning(
                "Location %s has no slug, skipping conditions write",
                location.name,
            )
            return []

        conditions = weather_data.condition_text if weather_data else None
        display_value = conditions or "--"
        key = f"kurokku:weather:{slug}:conditions"

        return [(key, display_value, self.temp_ttl)]

    def _get_alert_priority(
        self,
        event: str,
        severity: str | None = None,
        urgency: str | None = None,
    ) -> int:
        """
        Get priority level for an alert event.

        Matches event text case-insensitively against configured priority mappings.
        When multiple keywords match (e.g. "severe thunderstorm" and
        "severe thunderstorm watch"), the longest match wins so specificity
        beats configuration order. If no keyword matches, falls back to the
        CAP severity field (Extreme/Severe/Moderate/Minor/Unknown). When the
        CAP fallback is used and urgency is "Immediate", the priority is
        bumped up one level (minimum 0).

        Args:
            event: Alert event string (e.g., "Severe Thunderstorm Warning")
            severity: CAP severity (Extreme, Severe, Moderate, Minor, Unknown)
            urgency: CAP urgency (Immediate, Expected, Future, Past, Unknown)

        Returns:
            Priority level (0 = highest)
        """
        event_lower = event.lower()
        best_match: tuple[int, int] | None = None  # (keyword length, priority)
        for keyword, priority in self.alert_priorities.items():
            if keyword in event_lower and (
                best_match is None or len(keyword) > best_match[0]
            ):
                best_match = (len(keyword), priority)
        if best_match is not None:
            return best_match[1]

        priority = CAP_SEVERITY_PRIORITIES.get((severity or "").lower(), 5)
        if (urgency or "").lower() == "immediate":
            priority = max(0, priority - 1)
        return priority

    def _calculate_display_duration(self, message: str) -> str:
        """
        Calculate display duration based on message length.

        Args:
            message: The alert message text

        Returns:
            Display duration as a Go-style duration string (e.g., "8.4s")
        """
        duration = (
            len(message) * self.display_duration_per_char
        ) + self.display_duration_base
        return f"{round(duration, 1)}s"

    @staticmethod
    def _alert_key_suffix(alert: WeatherAlert) -> str:
        # Stable, opaque, redis-safe per-alert suffix. SHA-1 truncated to 12
        # hex chars gives a ~48-bit space — collision-safe for any realistic
        # number of concurrent alerts per slug. When the upstream alert has
        # no id (non-NOAA providers), fall back to a content hash so each
        # alert still gets a distinct key.
        if alert.alert_id:
            seed = alert.alert_id
        else:
            seed = f"{alert.event}|{alert.severity}|{alert.effective.isoformat()}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    def format_alerts(
        self, location: Location, alerts: list[WeatherAlert]
    ) -> tuple[str, dict[str, tuple[str, int]]]:
        """
        Build the desired Redis alert key state for a location.

        Args:
            location: Location model instance (must have slug)
            alerts: List of active weather alerts

        Returns:
            Tuple of (prefix, desired) where:
            - prefix: glob prefix matching all alert keys for this location
              (e.g. "kurokku:alert:weather:{slug}:"). Empty string if the
              location has no slug — caller should skip alert sync.
            - desired: mapping of full Redis key -> (value_json, ttl_seconds)
              for every alert that should currently exist. Caller diffs this
              against existing keys to compute the minimum set of writes.
        """
        slug = location.slug
        if not slug:
            logger.warning(
                "Location %s has no slug, skipping alert write",
                location.name,
            )
            return "", {}

        prefix = f"kurokku:alert:weather:{slug}:"
        desired: dict[str, tuple[str, int]] = {}
        now = datetime.now(UTC)

        for index, alert in enumerate(alerts):
            try:
                ttl = int((alert.expires - now).total_seconds())
                if ttl <= 0:
                    continue  # Skip expired alerts

                message = alert.event
                priority = self._get_alert_priority(
                    alert.event, alert.severity, alert.urgency
                )
                display_duration = self._calculate_display_duration(message)

                value = json.dumps(
                    {
                        "timestamp": alert.effective.isoformat(),
                        "message": message,
                        "priority": priority,
                        "display_duration": display_duration,
                        "delete_after_display": False,
                    }
                )

                key = prefix + self._alert_key_suffix(alert)
                desired[key] = (value, ttl)
            except Exception:
                logger.warning(
                    "Failed to format alert %d for location %s, skipping",
                    index,
                    location.name,
                    exc_info=True,
                )

        return prefix, desired
