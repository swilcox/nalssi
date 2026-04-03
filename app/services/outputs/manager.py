"""
Output manager for distributing weather data to configured backends.
"""

import asyncio
import contextlib
import json
import time

import structlog
from sqlalchemy.orm import Session

from app.models.backend_config import OutputBackendConfig
from app.models.location import Location
from app.services.outputs.base import BaseOutputBackend, WriteResult
from app.services.outputs.influxdb_backend import InfluxDBOutputBackend
from app.services.outputs.redis_backend import RedisOutputBackend
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = structlog.get_logger()

BACKEND_CLASSES = {
    "redis": RedisOutputBackend,
    "influxdb": InfluxDBOutputBackend,
}

# Default timeout for a single backend write operation (seconds)
DEFAULT_BACKEND_TIMEOUT = 5.0

# Circuit breaker settings
CIRCUIT_BREAKER_THRESHOLD = 3  # failures before opening circuit
CIRCUIT_BREAKER_COOLDOWN = 300  # seconds before retrying a tripped backend


def _parse_json_field(value: str | None) -> dict | None:
    """Parse a JSON text field, returning None if empty/null."""
    if not value:
        return None
    return json.loads(value)


def _location_matches_filter(location: Location, location_filter: dict | None) -> bool:
    """
    Check if a location matches the backend's location filter.

    Args:
        location: Location to check
        location_filter: Filter config (None = all, {"include": [...]}, {"exclude": [...]})

    Returns:
        True if location should be included
    """
    if location_filter is None:
        return True

    slug = location.slug or ""
    location_id = str(location.id)

    include = location_filter.get("include")
    if include is not None:
        return slug in include or location_id in include

    exclude = location_filter.get("exclude")
    if exclude is not None:
        return slug not in exclude and location_id not in exclude

    return True


def _create_backend(config: OutputBackendConfig) -> BaseOutputBackend | None:
    """
    Create a backend instance from a config row.

    Args:
        config: OutputBackendConfig model instance

    Returns:
        Backend instance or None if type is unsupported
    """
    backend_cls = BACKEND_CLASSES.get(config.backend_type)
    if not backend_cls:
        logger.warning("Unsupported backend type: %s", config.backend_type)
        return None

    connection_config = _parse_json_field(config.connection_config) or {}
    format_config = _parse_json_field(config.format_config)

    return backend_cls(
        name=config.name,
        config=connection_config,
        format_type=config.format_type,
        format_config=format_config,
    )


class CircuitBreaker:
    """
    Tracks per-backend failure counts and skips backends that are consistently failing.

    Prevents wasting time on backends that are down by "opening the circuit" after
    repeated failures, then retrying after a cooldown period.
    """

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        cooldown: float = CIRCUIT_BREAKER_COOLDOWN,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        # backend_name -> consecutive failure count
        self._failure_counts: dict[str, int] = {}
        # backend_name -> timestamp when circuit was opened
        self._open_since: dict[str, float] = {}

    def is_open(self, backend_name: str) -> bool:
        """Check if the circuit is open (backend should be skipped)."""
        if backend_name not in self._open_since:
            return False

        elapsed = time.monotonic() - self._open_since[backend_name]
        if elapsed >= self.cooldown:
            # Cooldown expired, allow a retry (half-open state)
            logger.info(
                "Circuit breaker cooldown expired for %s, allowing retry",
                backend_name,
            )
            return False

        return True

    def record_success(self, backend_name: str) -> None:
        """Record a successful write, resetting the failure counter."""
        self._failure_counts.pop(backend_name, None)
        self._open_since.pop(backend_name, None)

    def record_failure(self, backend_name: str) -> None:
        """Record a failed write, potentially opening the circuit."""
        count = self._failure_counts.get(backend_name, 0) + 1
        self._failure_counts[backend_name] = count

        if count >= self.threshold:
            self._open_since[backend_name] = time.monotonic()
            logger.warning(
                "Circuit breaker opened for %s after %d consecutive failures, "
                "will retry in %ds",
                backend_name,
                count,
                self.cooldown,
            )


class OutputManager:
    """Distributes weather data to all configured and enabled output backends."""

    def __init__(
        self,
        backend_timeout: float = DEFAULT_BACKEND_TIMEOUT,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.backend_timeout = backend_timeout
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    async def _write_single_backend(
        self,
        config: OutputBackendConfig,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> WriteResult:
        """
        Write to a single backend with timeout protection.

        Returns a WriteResult regardless of success or failure.
        """
        backend = _create_backend(config)
        if not backend:
            return WriteResult(
                success=False,
                backend_name=config.name,
                errors=[f"Unsupported backend type: {config.backend_type}"],
            )

        try:
            result = await asyncio.wait_for(
                backend.write(location, weather_data, alerts),
                timeout=self.backend_timeout,
            )

            if result.success:
                self.circuit_breaker.record_success(config.name)
                logger.info(
                    "Backend %s wrote %d keys for %s",
                    config.name,
                    result.keys_written,
                    location.name,
                )
            else:
                self.circuit_breaker.record_failure(config.name)
                logger.warning(
                    "Backend %s had errors for %s: %s",
                    config.name,
                    location.name,
                    result.errors,
                )

            return result

        except TimeoutError:
            self.circuit_breaker.record_failure(config.name)
            logger.error(
                "Backend %s timed out after %.1fs for %s",
                config.name,
                self.backend_timeout,
                location.name,
            )
            return WriteResult(
                success=False,
                backend_name=config.name,
                errors=[f"Timed out after {self.backend_timeout}s"],
            )
        except Exception as e:
            self.circuit_breaker.record_failure(config.name)
            logger.error(
                "Backend %s failed for %s: %s",
                config.name,
                location.name,
                e,
            )
            return WriteResult(
                success=False,
                backend_name=config.name,
                errors=[str(e)],
            )
        finally:
            with contextlib.suppress(Exception):
                await backend.close()

    async def distribute(
        self,
        db: Session,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> list[WriteResult]:
        """
        Distribute weather data to all matching backends concurrently.

        Each backend write is independent, runs with a timeout, and respects
        the circuit breaker. One failure doesn't affect others.

        Args:
            db: Database session for querying backend configs
            location: Location model instance
            weather_data: Normalized weather data (may be None)
            alerts: List of active weather alerts

        Returns:
            List of WriteResult from each backend
        """
        configs = (
            db.query(OutputBackendConfig)
            .filter(OutputBackendConfig.enabled == True)  # noqa: E712
            .all()
        )

        tasks = []
        skipped = []
        for config in configs:
            # Check location filter
            location_filter = _parse_json_field(config.location_filter)
            if not _location_matches_filter(location, location_filter):
                continue

            # Check circuit breaker
            if self.circuit_breaker.is_open(config.name):
                skipped.append(
                    WriteResult(
                        success=False,
                        backend_name=config.name,
                        errors=["Skipped: circuit breaker open"],
                    )
                )
                continue

            tasks.append(
                self._write_single_backend(config, location, weather_data, alerts)
            )

        # Run all backend writes concurrently
        results = []
        if tasks:
            results = list(await asyncio.gather(*tasks, return_exceptions=False))

        return results + skipped
