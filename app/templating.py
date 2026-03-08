"""
Jinja2 template configuration for server-rendered pages.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Weather condition icon mapping (condition_text -> icon class)
# Matches against lowercased condition_text substrings
_WEATHER_ICONS = [
    # Thunderstorms
    ("thunderstorm", "thunderstorm"),
    # Snow
    ("heavy snow", "snow-heavy"),
    ("snow shower", "snow"),
    ("snow grain", "snow"),
    ("snow", "snow"),
    ("blizzard", "snow-heavy"),
    ("sleet", "sleet"),
    ("ice", "sleet"),
    ("freezing rain", "sleet"),
    ("freezing drizzle", "sleet"),
    # Rain
    ("heavy rain", "rain-heavy"),
    ("violent rain", "rain-heavy"),
    ("moderate rain", "rain"),
    ("rain shower", "rain"),
    ("rain", "rain-light"),
    ("drizzle", "rain-light"),
    ("showers", "rain"),
    # Fog/Mist
    ("fog", "fog"),
    ("mist", "fog"),
    ("haze", "fog"),
    ("smoke", "fog"),
    # Cloudy
    ("overcast", "cloudy"),
    ("broken cloud", "cloudy"),
    ("scattered cloud", "partly-cloudy"),
    ("partly cloudy", "partly-cloudy"),
    ("mostly cloudy", "cloudy"),
    ("few cloud", "partly-cloudy"),
    ("mainly clear", "partly-cloudy"),
    # Clear
    ("clear", "clear"),
    ("sunny", "clear"),
    ("fair", "clear"),
]


def weather_icon(condition_text: str | None) -> str:
    """Map a condition text to an SVG weather icon class name."""
    if not condition_text:
        return "unknown"
    text = condition_text.lower()
    for keyword, icon_name in _WEATHER_ICONS:
        if keyword in text:
            return icon_name
    return "unknown"


templates.env.filters["weather_icon"] = weather_icon
