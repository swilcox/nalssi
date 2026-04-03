"""
Weather data API routes.
"""

import json
from datetime import UTC
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.location import Location
from app.schemas.weather import (
    CurrentWeatherResponse,
    ForecastPeriodResponse,
    ForecastResponse,
    WeatherAlertResponse,
)
from app.services.weather_apis.noaa import NOAAWeatherClient

router = APIRouter()
logger = structlog.get_logger()


@router.get(
    "/locations/{location_id}/weather/current",
    response_model=CurrentWeatherResponse,
)
async def get_current_weather(
    location_id: UUID,
    fresh: bool = False,
    include_raw: bool = False,
    db: Session = Depends(get_db),
):
    """
    Get current weather for a location.

    By default, returns cached data from the database. Use fresh=true to fetch live data.

    Args:
        location_id: Location UUID
        fresh: If True, fetch fresh data from weather API instead of cached data
        db: Database session

    Returns:
        Current weather data

    Raises:
        HTTPException: If location not found or weather fetch fails
    """
    from app.models.weather import WeatherData

    # Get location from database
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        logger.warning(
            "Location not found for weather request",
            location_id=str(location_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )

    # If fresh data requested, fetch from API
    if fresh:
        logger.info(
            "Fetching fresh weather data from API",
            location_id=str(location_id),
            location_name=location.name,
        )

        # Get weather from appropriate API
        if location.country_code == "US":
            client = NOAAWeatherClient()
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Only US locations supported currently",
            )

        try:
            weather_data = await client.get_current_weather(
                location.latitude, location.longitude
            )
            logger.info(
                "Successfully fetched fresh weather data",
                location_id=str(location_id),
                source_api=client.name,
                temperature=weather_data.temperature,
            )

            # Convert to response schema
            return CurrentWeatherResponse(
                location_id=location.id,
                location_name=location.name,
                temperature=weather_data.temperature,
                temperature_fahrenheit=weather_data.temperature_fahrenheit,
                condition_text=weather_data.condition_text,
                humidity=weather_data.humidity,
                pressure=weather_data.pressure,
                wind_speed=weather_data.wind_speed,
                wind_direction=weather_data.wind_direction,
                wind_gust=weather_data.wind_gust,
                visibility=weather_data.visibility,
                timestamp=weather_data.timestamp,
                source_api=client.name,
                raw_data=weather_data.raw_data if include_raw else None,
            )
        except Exception as e:
            logger.exception(
                "Failed to fetch fresh weather data",
                location_id=str(location_id),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch weather data: {str(e)}",
            ) from e

    # Return cached data from database
    logger.info(
        "Retrieving cached weather data",
        location_id=str(location_id),
        location_name=location.name,
    )

    # Get most recent weather data for this location
    latest_weather = (
        db.query(WeatherData)
        .filter(WeatherData.location_id == location_id)
        .order_by(WeatherData.timestamp.desc())
        .first()
    )

    if not latest_weather:
        logger.warning(
            "No cached weather data available",
            location_id=str(location_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weather data available for this location. Try fresh=true to fetch live data.",
        )

    logger.info(
        "Returning cached weather data",
        location_id=str(location_id),
        timestamp=latest_weather.timestamp,
        source_api=latest_weather.source_api,
    )

    # Parse raw_data from JSON text if requested
    raw_data = None
    if include_raw and latest_weather.raw_data:
        try:
            raw_data = json.loads(latest_weather.raw_data)
        except (json.JSONDecodeError, TypeError):
            raw_data = None

    # Convert to response schema
    return CurrentWeatherResponse(
        location_id=location.id,
        location_name=location.name,
        temperature=latest_weather.temperature,
        temperature_fahrenheit=latest_weather.temperature_fahrenheit,
        condition_text=latest_weather.condition_text,
        humidity=latest_weather.humidity,
        pressure=latest_weather.pressure,
        wind_speed=latest_weather.wind_speed,
        wind_direction=latest_weather.wind_direction,
        wind_gust=latest_weather.wind_gust,
        visibility=latest_weather.visibility,
        timestamp=latest_weather.timestamp,
        source_api=latest_weather.source_api,
        raw_data=raw_data,
    )


@router.get(
    "/locations/{location_id}/alerts",
    response_model=list[WeatherAlertResponse],
)
async def get_alerts(
    location_id: UUID, fresh: bool = False, db: Session = Depends(get_db)
):
    """
    Get active weather alerts for a location.

    By default, returns cached active alerts from the database. Use fresh=true to fetch live data.

    Args:
        location_id: Location UUID
        fresh: If True, fetch fresh data from weather API instead of cached data
        db: Database session

    Returns:
        List of active weather alerts

    Raises:
        HTTPException: If location not found or alert fetch fails
    """
    import json

    from app.models.alert import Alert

    # Get location from database
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        logger.warning(
            "Location not found for alerts request",
            location_id=str(location_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )

    # If fresh data requested, fetch from API
    if fresh:
        logger.info(
            "Fetching fresh weather alerts from API",
            location_id=str(location_id),
            location_name=location.name,
        )

        # Get alerts from appropriate API
        if location.country_code == "US":
            client = NOAAWeatherClient()
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Only US locations supported currently",
            )

        try:
            alerts = await client.get_alerts(location.latitude, location.longitude)
            logger.info(
                "Successfully fetched fresh alerts",
                location_id=str(location_id),
                alert_count=len(alerts),
            )

            # Convert to response schema
            return [
                WeatherAlertResponse(
                    event=alert.event,
                    headline=alert.headline,
                    severity=alert.severity,
                    urgency=alert.urgency,
                    effective=alert.effective,
                    expires=alert.expires,
                    areas=alert.areas,
                    description=alert.description,
                    instruction=alert.instruction,
                )
                for alert in alerts
            ]
        except Exception as e:
            logger.exception(
                "Failed to fetch fresh alerts",
                location_id=str(location_id),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to fetch alerts: {str(e)}",
            ) from e

    # Return cached active alerts from database
    logger.info(
        "Retrieving cached weather alerts",
        location_id=str(location_id),
        location_name=location.name,
    )

    # Get active alerts that haven't expired yet
    from datetime import datetime

    now = datetime.now(UTC)

    cached_alerts = (
        db.query(Alert)
        .filter(Alert.location_id == location_id)
        .filter(Alert.expires > now)  # Only active alerts
        .order_by(Alert.effective.desc())
        .all()
    )

    logger.info(
        "Returning cached alerts",
        location_id=str(location_id),
        alert_count=len(cached_alerts),
    )

    # Convert to response schema
    return [
        WeatherAlertResponse(
            event=alert.event,
            headline=alert.headline,
            severity=alert.severity,
            urgency=alert.urgency,
            effective=alert.effective,
            expires=alert.expires,
            areas=json.loads(alert.areas) if alert.areas else [],
            description=alert.description,
            instruction=alert.instruction,
        )
        for alert in cached_alerts
    ]


@router.get(
    "/locations/{location_id}/weather/forecast",
    response_model=ForecastResponse,
)
async def get_forecast(
    location_id: UUID, db: Session = Depends(get_db)
):
    """
    Get weather forecast for a location.

    Returns cached forecast periods from the database, ordered by start time.
    Only returns future periods (start_time >= now).

    Args:
        location_id: Location UUID
        db: Database session

    Returns:
        Forecast with list of periods
    """
    from datetime import UTC, datetime

    from app.models.forecast import Forecast

    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )

    now = datetime.now(UTC)

    forecasts = (
        db.query(Forecast)
        .filter(
            Forecast.location_id == location_id,
            Forecast.end_time > now,
        )
        .order_by(Forecast.start_time)
        .all()
    )

    periods = [
        ForecastPeriodResponse(
            start_time=f.start_time,
            end_time=f.end_time,
            temperature=f.temperature,
            temperature_fahrenheit=f.temperature_fahrenheit,
            temp_low=f.temp_low,
            temp_low_fahrenheit=f.temp_low_fahrenheit,
            feels_like=f.feels_like,
            humidity=f.humidity,
            pressure=f.pressure,
            wind_speed=f.wind_speed,
            wind_direction=f.wind_direction,
            wind_gust=f.wind_gust,
            precipitation_probability=f.precipitation_probability,
            precipitation_amount=f.precipitation_amount,
            cloud_cover=f.cloud_cover,
            visibility=f.visibility,
            uv_index=f.uv_index,
            condition_text=f.condition_text,
            condition_code=f.condition_code,
            is_daytime=f.is_daytime,
            detailed_forecast=f.detailed_forecast,
        )
        for f in forecasts
    ]

    # Determine source_api from first period, or default
    source_api = forecasts[0].source_api if forecasts else "unknown"

    return ForecastResponse(
        location_id=location.id,
        location_name=location.name,
        source_api=source_api,
        periods=periods,
    )
