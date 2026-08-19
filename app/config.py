"""
Application configuration management using Pydantic Settings.
"""

from importlib.metadata import PackageNotFoundError, version

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    _APP_VERSION = version("nalssi")
except PackageNotFoundError:
    # Fall back to reading pyproject.toml directly (e.g. dev without editable install)
    import tomllib
    from pathlib import Path

    _pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(_pyproject, "rb") as f:
        _APP_VERSION = tomllib.load(f)["project"]["version"]


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    All settings are immutable after creation (frozen).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        frozen=True,  # Make settings immutable
    )

    # Application
    APP_NAME: str = "nalssi"
    APP_VERSION: str = _APP_VERSION
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = Field(
        default=False,
        description="Use JSON formatted logs (enable for production)",
    )
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./nalssi.db"

    # Security
    SECRET_KEY: str = "change-this-in-production"
    API_KEY_ENCRYPTION_KEY: str = "change-this-in-production"

    # Weather APIs
    NOAA_API_BASE_URL: str = "https://api.weather.gov"
    OPEN_METEO_API_BASE_URL: str = "https://api.open-meteo.com/v1"
    WEATHERAPI_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    OPENWEATHER_API_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

    # Collection
    ENABLE_SCHEDULER: bool = Field(
        default=True,
        description="Enable automatic weather collection scheduler",
    )
    DEFAULT_COLLECTION_INTERVAL: int = Field(
        default=300,
        description="Default collection interval in seconds",
    )
    FORECAST_COLLECTION_INTERVAL: int = Field(
        default=3600,
        description="Forecast collection interval in seconds (default: 1 hour)",
    )
    MAX_CONCURRENT_COLLECTIONS: int = Field(
        default=5,
        description="Maximum number of concurrent collection tasks",
    )
    ALERT_PRIORITIES_FILE: str = Field(
        default="",
        description=(
            "Path to a YAML file overriding alert display priorities. Uses the "
            "same schema as the bundled defaults and is merged on top of them "
            "(only the keywords/severities it lists change). Empty = bundled "
            "defaults only. Read once at startup."
        ),
    )

    # Radar imagery
    RADAR_ENABLED: bool = Field(
        default=True,
        description="Enable periodic radar frame collection",
    )
    RADAR_WMS_BASE_URL: str = "https://opengeo.ncep.noaa.gov/geoserver/ows"
    RADAR_GEOMET_URL: str = Field(
        default="https://geo.weather.gc.ca/geomet",
        description="MSC GeoMet WMS endpoint, used for Canadian locations",
    )
    RADAR_HYDRO_WMS_URL: str = Field(
        default=(
            "https://basemap.nationalmap.gov/arcgis/services/"
            "USGSHydroCached/MapServer/WMSServer"
        ),
        description=(
            "WMS endpoint supplying shaded water for the radar basemap. "
            "Empty disables the water band."
        ),
    )
    RADAR_STORAGE_DIR: str = Field(
        default="./data/radar",
        description="Directory holding per-location radar frames and basemaps",
    )
    RADAR_COLLECTION_INTERVAL: int = Field(
        default=300,
        description="Radar collection interval in seconds",
    )
    RADAR_RETENTION_MINUTES: int = Field(
        default=120,
        description=(
            "How much radar history to keep, in minutes. The upstream service "
            "only offers a ~2 hour rolling window, so values above ~120 have "
            "no additional effect."
        ),
    )
    RADAR_VIEW_SPAN_KM: float = Field(
        default=240.0,
        description="Width/height of the radar view centered on each location, in km",
    )
    RADAR_IMAGE_SIZE: int = Field(
        default=600,
        description="Radar image width and height in pixels (square)",
    )
    RADAR_MAX_CONCURRENT_FETCHES: int = Field(
        default=4,
        description="Max concurrent radar frame downloads (politeness cap)",
    )
    RADAR_RANGE_RINGS_KM: str = Field(
        default="50,100",
        description=(
            "Comma-separated distances, in km, to draw as range rings around "
            "each location. Empty disables rings. Rings wider than half the "
            "view span are ignored since they fall outside the image."
        ),
    )

    @property
    def radar_range_rings(self) -> list[float]:
        """
        Parse RADAR_RANGE_RINGS_KM into a sorted list of distances.

        Unparseable entries are dropped rather than failing startup, since a
        malformed ring list shouldn't take the whole service down.
        """
        rings = []
        for part in self.RADAR_RANGE_RINGS_KM.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                value = float(part)
            except ValueError:
                continue
            if value > 0:
                rings.append(value)
        return sorted(set(rings))

    # Redis (optional)
    REDIS_URL: str = "redis://localhost:6379/0"

    # InfluxDB (optional)
    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = ""
    INFLUXDB_ORG: str = ""
    INFLUXDB_BUCKET: str = "weather"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = Field(
        default=8000,
        description="API server port",
    )

    @field_validator(
        "DEFAULT_COLLECTION_INTERVAL",
        "FORECAST_COLLECTION_INTERVAL",
        "RADAR_COLLECTION_INTERVAL",
    )
    @classmethod
    def validate_collection_interval(cls, v: int) -> int:
        """Validate that collection interval is positive."""
        if v <= 0:
            raise ValueError("Collection interval must be positive")
        return v

    @field_validator("RADAR_VIEW_SPAN_KM")
    @classmethod
    def validate_radar_span(cls, v: float) -> float:
        """Validate that the radar view span is positive."""
        if v <= 0:
            raise ValueError("Radar view span must be positive")
        return v

    @field_validator("RADAR_IMAGE_SIZE")
    @classmethod
    def validate_radar_image_size(cls, v: int) -> int:
        """Validate the radar image size against the WMS server's limits."""
        if v < 1 or v > 4096:
            raise ValueError("Radar image size must be between 1 and 4096")
        return v

    @field_validator("API_PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate that port is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("MAX_CONCURRENT_COLLECTIONS")
    @classmethod
    def validate_max_concurrent(cls, v: int) -> int:
        """Validate that max concurrent collections is positive."""
        if v <= 0:
            raise ValueError("Max concurrent collections must be positive")
        return v


# Global settings instance
settings = Settings()
