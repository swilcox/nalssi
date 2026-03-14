"""
Forecast page route.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.forecast import Forecast
from app.models.location import Location
from app.templating import templates

router = APIRouter()


def build_forecast_items(db: Session) -> list[dict]:
    """Build forecast data grouped by location for display."""
    now = datetime.now(UTC)
    locations = db.query(Location).filter(Location.enabled == True).order_by(Location.name).all()

    items = []
    for loc in locations:
        periods = (
            db.query(Forecast)
            .filter(
                Forecast.location_id == loc.id,
                Forecast.end_time > now,
            )
            .order_by(Forecast.start_time)
            .all()
        )

        if not periods:
            continue

        period_items = []
        for p in periods:
            period_items.append(
                {
                    "start_time": p.start_time.strftime("%a %I:%M %p")
                    if p.start_time
                    else "",
                    "end_time": p.end_time.strftime("%a %I:%M %p")
                    if p.end_time
                    else "",
                    "date_label": p.start_time.strftime("%a %b %d")
                    if p.start_time
                    else "",
                    "temperature": p.temperature,
                    "temperature_fahrenheit": p.temperature_fahrenheit,
                    "condition_text": p.condition_text,
                    "is_daytime": p.is_daytime,
                    "wind_speed": p.wind_speed,
                    "wind_direction": p.wind_direction,
                    "precipitation_probability": p.precipitation_probability,
                    "humidity": p.humidity,
                    "detailed_forecast": p.detailed_forecast,
                }
            )

        items.append(
            {
                "location_name": loc.name,
                "slug": loc.slug or str(loc.id),
                "source_api": periods[0].source_api if periods else "",
                "periods": period_items,
            }
        )

    return items


@router.get("/forecast")
def forecast_page(request: Request, db: Session = Depends(get_db)):
    """Weather forecast for all locations."""
    items = build_forecast_items(db)

    template = (
        "forecast/_content.html"
        if request.headers.get("HX-Request")
        else "forecast/list.html"
    )

    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "forecast_locations": items,
            "nav_active": "forecast",
        },
    )
