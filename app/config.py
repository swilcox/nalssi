"""
Application configuration management using Pydantic Settings.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    APP_VERSION: str = "0.1.0"
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

    @field_validator("DEFAULT_COLLECTION_INTERVAL", "FORECAST_COLLECTION_INTERVAL")
    @classmethod
    def validate_collection_interval(cls, v: int) -> int:
        """Validate that collection interval is positive."""
        if v <= 0:
            raise ValueError("Collection interval must be positive")
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
