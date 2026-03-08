"""
Base class for output backends.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.location import Location
from app.services.weather_apis.base import WeatherAlert, WeatherData


@dataclass
class WriteResult:
    """Result of a write operation to an output backend."""

    success: bool
    backend_name: str
    keys_written: int = 0
    keys_deleted: int = 0
    errors: list[str] = field(default_factory=list)


class BaseOutputBackend(ABC):
    """Abstract base class for output backends."""

    def __init__(self, name: str, config: dict):
        """
        Initialize the output backend.

        Args:
            name: Name of this backend instance
            config: Connection and format configuration
        """
        self.name = name
        self.config = config

    @abstractmethod
    async def write(
        self,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> WriteResult:
        """
        Write weather data and alerts to the backend.

        Args:
            location: Location model instance
            weather_data: Normalized weather data (may be None)
            alerts: List of active weather alerts

        Returns:
            WriteResult with operation details
        """

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connectivity to the backend.

        Returns:
            True if connection is successful
        """

    async def close(self) -> None:  # noqa: B027
        """Clean up resources. Override if needed."""
