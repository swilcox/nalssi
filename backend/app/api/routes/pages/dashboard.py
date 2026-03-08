"""
Dashboard page route.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.alert import Alert
from app.models.location import Location
from app.models.weather import WeatherData
from app.templating import templates

router = APIRouter()


def build_dashboard_items(db: Session) -> list[dict]:
    """Build the list of location items with weather data and alert counts."""
    locations = db.query(Location).order_by(Location.name).all()
    now = datetime.now(UTC)

    items = []
    for loc in locations:
        # Latest weather data
        latest = (
            db.query(WeatherData)
            .filter(WeatherData.location_id == loc.id)
            .order_by(desc(WeatherData.timestamp))
            .first()
        )

        # Active alert count
        alert_count = (
            db.query(func.count(Alert.id))
            .filter(Alert.location_id == loc.id, Alert.expires > now)
            .scalar()
        )

        weather_info = None
        if latest:
            # Parse raw_data JSON if available
            raw_data = None
            if latest.raw_data:
                try:
                    raw_data = json.loads(latest.raw_data)
                except (json.JSONDecodeError, TypeError):
                    raw_data = None

            weather_info = {
                "temperature": latest.temperature,
                "temperature_fahrenheit": latest.temperature_fahrenheit,
                "condition_text": latest.condition_text,
                "humidity": latest.humidity,
                "wind_speed": latest.wind_speed,
                "source_api": latest.source_api,
                "timestamp": latest.timestamp.strftime("%Y-%m-%d %H:%M UTC")
                if latest.timestamp
                else "",
                "raw_data": raw_data,
            }

        items.append(
            {
                "slug": loc.slug or str(loc.id),
                "name": loc.name,
                "enabled": loc.enabled,
                "weather": weather_info,
                "alert_count": alert_count,
            }
        )

    return items


def get_active_alert_count(db: Session) -> int:
    """Get total active alert count across all locations."""
    now = datetime.now(UTC)
    return (
        db.query(func.count(Alert.id)).filter(Alert.expires > now).scalar() or 0
    )


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Weather dashboard with cards for all locations."""
    items = build_dashboard_items(db)
    nav_alert_count = get_active_alert_count(db)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "locations": items,
            "nav_alert_count": nav_alert_count,
        },
    )
