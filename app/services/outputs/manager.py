"""
Output manager for distributing weather data to configured backends.
"""

import contextlib
import json
import logging

from sqlalchemy.orm import Session

from app.models.backend_config import OutputBackendConfig
from app.models.location import Location
from app.services.outputs.base import WriteResult
from app.services.outputs.influxdb_backend import InfluxDBOutputBackend
from app.services.outputs.redis_backend import RedisOutputBackend
from app.services.weather_apis.base import WeatherAlert, WeatherData

logger = logging.getLogger(__name__)

BACKEND_CLASSES = {
    "redis": RedisOutputBackend,
    "influxdb": InfluxDBOutputBackend,
}


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


def _create_backend(config: OutputBackendConfig):
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


class OutputManager:
    """Distributes weather data to all configured and enabled output backends."""

    async def distribute(
        self,
        db: Session,
        location: Location,
        weather_data: WeatherData | None,
        alerts: list[WeatherAlert],
    ) -> list[WriteResult]:
        """
        Distribute weather data to all matching backends.

        Each backend write is independent - one failure doesn't affect others.

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

        results = []
        for config in configs:
            # Check location filter
            location_filter = _parse_json_field(config.location_filter)
            if not _location_matches_filter(location, location_filter):
                continue

            backend = _create_backend(config)
            if not backend:
                continue

            try:
                result = await backend.write(location, weather_data, alerts)
                results.append(result)

                if result.success:
                    logger.info(
                        "Backend %s wrote %d keys for %s",
                        config.name,
                        result.keys_written,
                        location.name,
                    )
                else:
                    logger.warning(
                        "Backend %s had errors for %s: %s",
                        config.name,
                        location.name,
                        result.errors,
                    )
            except Exception as e:
                logger.error(
                    "Backend %s failed for %s: %s",
                    config.name,
                    location.name,
                    e,
                )
                results.append(
                    WriteResult(
                        success=False,
                        backend_name=config.name,
                        errors=[str(e)],
                    )
                )
            finally:
                with contextlib.suppress(Exception):
                    await backend.close()

        return results
