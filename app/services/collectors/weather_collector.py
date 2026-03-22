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
from app.models.forecast import Forecast
from app.models.location import Location
from app.models.weather import WeatherData
from app.services.broadcast import manager as broadcast_manager
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

            # Broadcast live updates to WebSocket clients
            await self._broadcast_updates(db)

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
        client = self._get_client_for_location(location)

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
                    # Track what changed for logging
                    changes = []
                    if existing.severity != alert.severity:
                        changes.append(
                            f"severity: {existing.severity} -> {alert.severity}"
                        )
                    if existing.urgency != alert.urgency:
                        changes.append(
                            f"urgency: {existing.urgency} -> {alert.urgency}"
                        )
                    if existing.expires != alert.expires:
                        changes.append(
                            f"expires: {existing.expires} -> {alert.expires}"
                        )
                    if existing.event != alert.event:
                        changes.append(
                            f"event: {existing.event} -> {alert.event}"
                        )

                    # Update mutable fields on the existing alert
                    existing.event = alert.event
                    existing.headline = alert.headline
                    existing.severity = alert.severity
                    existing.urgency = alert.urgency
                    existing.certainty = alert.certainty
                    existing.category = alert.category
                    existing.response_type = alert.response_type
                    existing.sender_name = alert.sender_name
                    existing.status = alert.status
                    existing.message_type = alert.message_type
                    existing.effective = alert.effective
                    existing.expires = alert.expires
                    existing.onset = alert.onset
                    existing.ends = alert.ends
                    existing.areas = (
                        json.dumps(alert.areas) if alert.areas else None
                    )
                    existing.description = alert.description
                    existing.instruction = alert.instruction
                    existing.fetched_at = datetime.now(UTC)
                    updated_count += 1

                    if changes:
                        logger.info(
                            f"Alert updated for {location.name}: "
                            f"{alert.event} ({alert.alert_id}): "
                            f"{', '.join(changes)}",
                            extra={
                                "location_id": str(location.id),
                                "alert_id": alert.alert_id,
                                "event": alert.event,
                                "severity": alert.severity,
                                "changes": changes,
                            },
                        )
                    else:
                        logger.debug(
                            f"Alert unchanged for {location.name}: "
                            f"{alert.event} ({alert.alert_id})",
                            extra={
                                "location_id": str(location.id),
                                "alert_id": alert.alert_id,
                                "event": alert.event,
                            },
                        )
                else:
                    db_alert = Alert(
                        location_id=location.id,
                        alert_id=alert.alert_id,
                        source_api=client.name,
                        event=alert.event,
                        headline=alert.headline,
                        severity=alert.severity,
                        urgency=alert.urgency,
                        certainty=alert.certainty,
                        category=alert.category,
                        response_type=alert.response_type,
                        sender_name=alert.sender_name,
                        status=alert.status,
                        message_type=alert.message_type,
                        effective=alert.effective,
                        expires=alert.expires,
                        onset=alert.onset,
                        ends=alert.ends,
                        areas=(
                            json.dumps(alert.areas) if alert.areas else None
                        ),
                        description=alert.description,
                        instruction=alert.instruction,
                    )
                    db.add(db_alert)
                    new_count += 1
                    logger.info(
                        f"New alert for {location.name}: {alert.event} "
                        f"(severity={alert.severity}, urgency={alert.urgency}, "
                        f"expires={alert.expires})",
                        extra={
                            "location_id": str(location.id),
                            "alert_id": alert.alert_id,
                            "event": alert.event,
                            "severity": alert.severity,
                            "urgency": alert.urgency,
                            "expires": str(alert.expires) if alert.expires else None,
                            "headline": alert.headline,
                        },
                    )

            logger.info(
                f"Alert check for {location.name}: {len(alerts)} fetched, "
                f"{new_count} new, {updated_count} updated",
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

    async def _broadcast_updates(self, db: Session) -> None:
        """Broadcast updated dashboard cards and alerts to WebSocket clients."""
        if not broadcast_manager.active_connections:
            return

        try:
            from app.api.routes.pages.alerts import build_alert_items
            from app.api.routes.pages.dashboard import (
                build_dashboard_items,
                get_active_alert_count,
            )
            from app.api.routes.pages.system import (
                build_last_collections,
                build_system_stats,
            )
            from app.templating import templates

            items = build_dashboard_items(db)
            alert_count = get_active_alert_count(db)
            alert_items = build_alert_items(db)
            system_stats = build_system_stats(db)
            last_collections = build_last_collections(db)

            # Render each weather card as an OOB swap fragment
            fragments = []
            for item in items:
                html = templates.get_template("dashboard/_card.html").render(
                    slug=item["slug"],
                    name=item["name"],
                    weather=item["weather"],
                    alert_count=item["alert_count"],
                    enabled=item["enabled"],
                    oob=True,
                )
                fragments.append(html)

            # Add nav alert badge OOB update
            badge_html = templates.get_template("_alert_badge.html").render(
                alert_count=alert_count,
            )
            fragments.append(badge_html)

            # Add alerts list OOB update (for clients on the alerts page)
            alerts_html = templates.get_template("alerts/_list_content.html").render(
                alerts=alert_items,
                alert_count=len(alert_items),
            )
            fragments.append(alerts_html)

            # Add system stats OOB update
            stats_html = templates.get_template("system/_stats.html").render(
                oob=True,
                **system_stats,
            )
            fragments.append(stats_html)

            # Add last collections OOB update
            collections_html = templates.get_template(
                "system/_collections.html"
            ).render(
                oob=True,
                last_collections=last_collections,
            )
            fragments.append(collections_html)

            message = "\n".join(fragments)
            await broadcast_manager.broadcast(message)

            logger.debug(
                "Broadcast weather, alert, and system updates to WebSocket clients",
                extra={
                    "card_count": len(items),
                    "alert_count": len(alert_items),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to broadcast WebSocket updates: {e}",
                extra={"error": str(e)},
            )

    def _get_client_for_location(self, location: Location):
        """Get the appropriate weather client for a location."""
        if location.preferred_api == "open-meteo":
            return self.open_meteo_client
        elif location.preferred_api == "openweather":
            return self.openweather_client
        elif location.preferred_api == "noaa" or location.country_code == "US":
            return self.noaa_client
        else:
            return self.open_meteo_client

    async def collect_all_forecasts(self) -> dict[str, int]:
        """
        Collect forecast data for all enabled locations.
        Runs on a separate (longer) interval from current weather collection.

        Returns:
            Dictionary with collection statistics
        """
        logger.info("Starting forecast collection cycle")
        stats = {"success_count": 0, "error_count": 0, "total_locations": 0}

        db = SessionLocal()
        try:
            locations = db.query(Location).filter(Location.enabled == True).all()
            stats["total_locations"] = len(locations)

            for location in locations:
                try:
                    await self._collect_forecasts_for_location(db, location)
                    stats["success_count"] += 1
                except Exception as e:
                    stats["error_count"] += 1
                    logger.error(
                        f"Failed to collect forecast for {location.name}",
                        extra={
                            "location_id": str(location.id),
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            db.commit()

            logger.info(
                "Forecast collection cycle completed",
                extra={
                    "total": stats["total_locations"],
                    "success": stats["success_count"],
                    "errors": stats["error_count"],
                },
            )

        except Exception as e:
            logger.error(
                "Critical error during forecast collection",
                extra={"error": str(e)},
                exc_info=True,
            )
            db.rollback()
        finally:
            db.close()

        return stats

    async def _collect_forecasts_for_location(
        self, db: Session, location: Location
    ) -> None:
        """Fetch and store forecast periods for a location."""
        client = self._get_client_for_location(location)

        forecast_periods = await client.get_forecast(
            location.latitude, location.longitude
        )
        new_forecasts = 0
        updated_forecasts = 0

        for period in forecast_periods:
            # Upsert by (location_id, source_api, start_time)
            existing = (
                db.query(Forecast)
                .filter(
                    Forecast.location_id == location.id,
                    Forecast.source_api == client.name,
                    Forecast.start_time == period.start_time,
                )
                .first()
            )

            if existing:
                existing.end_time = period.end_time
                existing.temperature = period.temperature
                existing.temperature_fahrenheit = period.temperature_fahrenheit
                existing.temp_low = period.temp_low
                existing.temp_low_fahrenheit = period.temp_low_fahrenheit
                existing.feels_like = period.feels_like
                existing.humidity = period.humidity
                existing.pressure = period.pressure
                existing.wind_speed = period.wind_speed
                existing.wind_direction = period.wind_direction
                existing.wind_gust = period.wind_gust
                existing.precipitation_probability = period.precipitation_probability
                existing.precipitation_amount = period.precipitation_amount
                existing.cloud_cover = period.cloud_cover
                existing.visibility = period.visibility
                existing.uv_index = period.uv_index
                existing.condition_text = period.condition_text
                existing.condition_code = period.condition_code
                existing.is_daytime = period.is_daytime
                existing.detailed_forecast = period.detailed_forecast
                existing.fetched_at = datetime.now(UTC)
                updated_forecasts += 1
            else:
                db_forecast = Forecast(
                    location_id=location.id,
                    source_api=client.name,
                    start_time=period.start_time,
                    end_time=period.end_time,
                    temperature=period.temperature,
                    temperature_fahrenheit=period.temperature_fahrenheit,
                    temp_low=period.temp_low,
                    temp_low_fahrenheit=period.temp_low_fahrenheit,
                    feels_like=period.feels_like,
                    humidity=period.humidity,
                    pressure=period.pressure,
                    wind_speed=period.wind_speed,
                    wind_direction=period.wind_direction,
                    wind_gust=period.wind_gust,
                    precipitation_probability=period.precipitation_probability,
                    precipitation_amount=period.precipitation_amount,
                    cloud_cover=period.cloud_cover,
                    visibility=period.visibility,
                    uv_index=period.uv_index,
                    condition_text=period.condition_text,
                    condition_code=period.condition_code,
                    is_daytime=period.is_daytime,
                    detailed_forecast=period.detailed_forecast,
                )
                db.add(db_forecast)
                new_forecasts += 1

        logger.info(
            f"Forecast for {location.name}: {len(forecast_periods)} periods, "
            f"{new_forecasts} new, {updated_forecasts} updated",
            extra={
                "location_id": str(location.id),
                "total_periods": len(forecast_periods),
                "new_forecasts": new_forecasts,
                "updated_forecasts": updated_forecasts,
            },
        )

    def collect_all_forecasts_sync(self) -> dict[str, int]:
        """Synchronous wrapper for collect_all_forecasts() for use with APScheduler."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self.collect_all_forecasts()
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.collect_all_forecasts())
        except RuntimeError:
            return asyncio.run(self.collect_all_forecasts())

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
