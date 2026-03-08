"""
Weather data collection service.

Periodically fetches weather data for all enabled locations and stores in database.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.alert import Alert
from app.models.location import Location
from app.models.weather import WeatherData
from app.services.outputs.manager import OutputManager
from app.services.weather_apis.noaa import NOAAWeatherClient
from app.services.weather_apis.open_meteo import OpenMeteoClient
from app.services.weather_apis.openweather import OpenWeatherClient

logger = logging.getLogger(__name__)


class WeatherCollector:
    """
    Collects weather data for enabled locations and stores in database.
    """

    def __init__(self):
        """Initialize the weather collector."""
        self.noaa_client = NOAAWeatherClient()
        self.open_meteo_client = OpenMeteoClient()
        self.openweather_client = OpenWeatherClient()
        self.output_manager = OutputManager()
        logger.info("Weather collector initialized")

    async def collect_all(self) -> dict[str, int]:
        """
        Collect weather data for all enabled locations.

        Returns:
            Dictionary with collection statistics (success_count, error_count)
        """
        logger.info("Starting weather collection cycle")
        stats = {"success_count": 0, "error_count": 0, "total_locations": 0}

        db = SessionLocal()
        try:
            # Get all enabled locations
            locations = db.query(Location).filter(Location.enabled == True).all()
            stats["total_locations"] = len(locations)

            logger.info(
                f"Found {len(locations)} enabled locations for collection",
                extra={"location_count": len(locations)},
            )

            # Collect weather for each location
            for location in locations:
                try:
                    await self._collect_for_location(db, location)
                    stats["success_count"] += 1
                except Exception as e:
                    stats["error_count"] += 1
                    logger.error(
                        f"Failed to collect weather for location {location.name}",
                        extra={
                            "location_id": str(location.id),
                            "location_name": location.name,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            # Commit all changes
            db.commit()

            logger.info(
                "Weather collection cycle completed",
                extra={
                    "total": stats["total_locations"],
                    "success": stats["success_count"],
                    "errors": stats["error_count"],
                },
            )

        except Exception as e:
            logger.error(
                "Critical error during weather collection",
                extra={"error": str(e)},
                exc_info=True,
            )
            db.rollback()
        finally:
            db.close()

        return stats

    async def _collect_for_location(self, db: Session, location: Location) -> None:
        """
        Collect weather data for a specific location.

        Args:
            db: Database session
            location: Location to collect weather for

        Raises:
            Exception: If weather collection fails
        """
        logger.info(
            f"Collecting weather for {location.name}",
            extra={
                "location_id": str(location.id),
                "location_name": location.name,
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
        )

        # Get appropriate weather client based on preferred_api and country
        if location.preferred_api == "open-meteo":
            client = self.open_meteo_client
        elif location.preferred_api == "openweather":
            client = self.openweather_client
        elif location.preferred_api == "noaa" or location.country_code == "US":
            client = self.noaa_client
        else:
            client = self.open_meteo_client

        # Fetch current weather
        weather_data = await client.get_current_weather(
            location.latitude, location.longitude
        )

        # Serialize raw_data to JSON string for storage
        raw_data_str = None
        if weather_data.raw_data is not None:
            raw_data_str = json.dumps(weather_data.raw_data)

        # Store in database
        db_weather = WeatherData(
            location_id=location.id,
            timestamp=weather_data.timestamp,
            source_api=client.name,
            temperature=weather_data.temperature,
            temperature_fahrenheit=weather_data.temperature_fahrenheit,
            condition_text=weather_data.condition_text,
            humidity=weather_data.humidity,
            pressure=weather_data.pressure,
            wind_speed=weather_data.wind_speed,
            wind_direction=weather_data.wind_direction,
            wind_gust=weather_data.wind_gust,
            visibility=weather_data.visibility,
            cloud_cover=weather_data.cloud_cover,
            feels_like=weather_data.feels_like,
            uv_index=weather_data.uv_index,
            precipitation=weather_data.precipitation,
            raw_data=raw_data_str,
        )

        db.add(db_weather)

        # Fetch and store weather alerts
        alerts = []
        try:
            alerts = await client.get_alerts(location.latitude, location.longitude)
            new_count = 0
            updated_count = 0

            for alert in alerts:
                # Upsert: look up existing alert by dedup key, update or insert
                existing = (
                    db.query(Alert)
                    .filter(
                        Alert.location_id == location.id,
                        Alert.alert_id == alert.alert_id,
                        Alert.source_api == client.name,
                    )
                    .first()
                )

                if existing:
                    # Update mutable fields on the existing alert
                    existing.event = alert.event
                    existing.headline = alert.headline
                    existing.severity = alert.severity
                    existing.urgency = alert.urgency
                    existing.certainty = getattr(alert, "certainty", None)
                    existing.effective = alert.effective
                    existing.expires = alert.expires
                    existing.onset = getattr(alert, "onset", None)
                    existing.ends = getattr(alert, "ends", None)
                    existing.areas = (
                        json.dumps(alert.areas) if alert.areas else None
                    )
                    existing.description = alert.description
                    existing.instruction = alert.instruction
                    existing.fetched_at = datetime.now(UTC)
                    updated_count += 1
                else:
                    db_alert = Alert(
                        location_id=location.id,
                        alert_id=alert.alert_id,
                        source_api=client.name,
                        event=alert.event,
                        headline=alert.headline,
                        severity=alert.severity,
                        urgency=alert.urgency,
                        certainty=getattr(alert, "certainty", None),
                        effective=alert.effective,
                        expires=alert.expires,
                        onset=getattr(alert, "onset", None),
                        ends=getattr(alert, "ends", None),
                        areas=(
                            json.dumps(alert.areas) if alert.areas else None
                        ),
                        description=alert.description,
                        instruction=alert.instruction,
                    )
                    db.add(db_alert)
                    new_count += 1

            if new_count > 0 or updated_count > 0:
                logger.info(
                    f"Alerts for {location.name}: {new_count} new, {updated_count} updated",
                    extra={
                        "location_id": str(location.id),
                        "new_alerts": new_count,
                        "updated_alerts": updated_count,
                        "total_fetched": len(alerts),
                    },
                )
        except Exception as e:
            logger.warning(
                f"Failed to fetch/store alerts for {location.name}: {str(e)}",
                extra={
                    "location_id": str(location.id),
                    "error": str(e),
                },
            )
            # Don't fail the whole collection if alerts fail

        logger.info(
            f"Weather data stored for {location.name}",
            extra={
                "location_id": str(location.id),
                "temperature": weather_data.temperature,
                "source_api": client.name,
            },
        )

        # Distribute to output backends (fire-and-forget, failures don't break collection)
        try:
            await self.output_manager.distribute(db, location, weather_data, alerts)
        except Exception as e:
            logger.warning(
                f"Output distribution failed for {location.name}: {e}",
                extra={
                    "location_id": str(location.id),
                    "error": str(e),
                },
            )

    def collect_all_sync(self) -> dict[str, int]:
        """
        Synchronous wrapper for collect_all() for use with APScheduler.

        Returns:
            Dictionary with collection statistics
        """
        try:
            # Try to get existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running (e.g., in tests), create a new task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.collect_all())
                    return future.result()
            else:
                # No running loop, safe to use asyncio.run
                return loop.run_until_complete(self.collect_all())
        except RuntimeError:
            # No event loop at all
            return asyncio.run(self.collect_all())


# Global collector instance
_collector: WeatherCollector | None = None


def get_collector() -> WeatherCollector:
    """
    Get or create the global weather collector instance.

    Returns:
        WeatherCollector instance
    """
    global _collector
    if _collector is None:
        _collector = WeatherCollector()
    return _collector
