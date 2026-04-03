"""
Kurokku format transform for led-kurokku Redis integration.

Produces Redis keys/values in the exact format that led-kurokku expects.
"""

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
    "ice storm": 1,
    "flood": 2,
    "winter storm": 2,
    "high wind": 2,
    "excessive heat": 2,
    "fire weather": 2,
    "wind chill": 3,
    "freeze": 3,
    "frost": 3,
    "heat advisory": 3,
    "wind advisory": 3,
    "dense fog": 3,
    "winter weather": 4,
    "special weather": 4,
}


class KurokuuFormatTransform:
    """
    Transforms weather data into the key/value format expected by led-kurokku.

    Redis key patterns:
        Temperature: kurokku:weather:{slug}:temp = "44°F"  (TTL 3600s)
        Alerts: kurokku:alert:weather:{slug}:{index} = JSON  (TTL from expiration)
    """

    DEFAULT_TEMP_TTL = 3600  # 1 hour
    DISPLAY_DURATION_BASE = 3.0  # seconds
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
        self.temp_ttl = self.format_config.get("temp_ttl", self.DEFAULT_TEMP_TTL)

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

    def _get_alert_priority(self, event: str) -> int:
        """
        Get priority level for an alert event.

        Matches event text case-insensitively against configured priority mappings.
        Falls back to priority 5 (lowest) if no match found.

        Args:
            event: Alert event string (e.g., "Severe Thunderstorm Warning")

        Returns:
            Priority level (0 = highest)
        """
        event_lower = event.lower()
        for keyword, priority in self.alert_priorities.items():
            if keyword in event_lower:
                return priority
        return 5  # Default low priority

    def _calculate_display_duration(self, message: str) -> str:
        """
        Calculate display duration based on message length.

        Args:
            message: The alert message text

        Returns:
            Display duration as a Go-style duration string (e.g., "8.4s")
        """
        duration = (
            len(message) * self.DISPLAY_DURATION_PER_CHAR
        ) + self.DISPLAY_DURATION_BASE
        return f"{round(duration, 1)}s"

    def format_alerts(
        self, location: Location, alerts: list[WeatherAlert]
    ) -> tuple[list[str], list[tuple[str, str, int]]]:
        """
        Format alerts into Redis key/value/ttl tuples.

        Args:
            location: Location model instance (must have slug)
            alerts: List of active weather alerts

        Returns:
            Tuple of (delete_patterns, [(key, value, ttl)])
            - delete_patterns: glob patterns of keys to delete before writing
            - list of (key, value, ttl) tuples for new alert keys
        """
        slug = location.slug
        if not slug:
            logger.warning(
                "Location %s has no slug, skipping alert write",
                location.name,
            )
            return [], []

        delete_patterns = [f"kurokku:alert:weather:{slug}:*"]
        entries = []

        now = datetime.now(UTC)

        for index, alert in enumerate(alerts):
            try:
                # Calculate TTL from expiration time
                ttl = int((alert.expires - now).total_seconds())
                if ttl <= 0:
                    continue  # Skip expired alerts

                message = alert.event
                priority = self._get_alert_priority(alert.event)
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

                key = f"kurokku:alert:weather:{slug}:{index}"
                entries.append((key, value, ttl))
            except Exception:
                logger.warning(
                    "Failed to format alert %d for location %s, skipping",
                    index,
                    location.name,
                    exc_info=True,
                )

        return delete_patterns, entries
