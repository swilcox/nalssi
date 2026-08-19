"""
Forecast page routes.

``/forecast`` lists every location with a short outlook; ``/forecast/{slug}`` is
the per-location detail view with every upcoming period. The split keeps the
list readable as locations are added, rather than stacking full 14-period grids
down one page.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.pages import get_location_by_slug, location_slug
from app.models.forecast import Forecast
from app.models.location import Location
from app.templating import templates

router = APIRouter()

# How many upcoming periods the list view previews per location.
SUMMARY_PERIOD_COUNT = 4


def _period_dict(p: Forecast) -> dict:
    """Flatten a Forecast row into the shape the templates expect."""
    return {
        "start_time": p.start_time.strftime("%a %I:%M %p") if p.start_time else "",
        "end_time": p.end_time.strftime("%a %I:%M %p") if p.end_time else "",
        "date_label": p.start_time.strftime("%a %b %d") if p.start_time else "",
        "short_label": p.start_time.strftime("%a") if p.start_time else "",
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


def _upcoming_periods(db: Session, location: Location) -> tuple[list[dict], str]:
    """
    Get a location's upcoming forecast periods, newest fetch winning.

    Args:
        db: Database session
        location: Location to load periods for

    Returns:
        Tuple of (period dicts in chronological order, source api name).
    """
    now = datetime.now(UTC)
    periods = (
        db.query(Forecast)
        .filter(
            Forecast.location_id == location.id,
            Forecast.end_time > now,
        )
        .order_by(Forecast.start_time, Forecast.fetched_at.desc())
        .all()
    )

    if not periods:
        return [], ""

    # Deduplicate: keep only the latest forecast per (date, is_daytime)
    seen: set[tuple[str, bool | None]] = set()
    deduped: list[Forecast] = []
    for p in periods:
        key = (
            p.start_time.strftime("%Y-%m-%d") if p.start_time else "",
            p.is_daytime,
        )
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    return [_period_dict(p) for p in deduped], periods[0].source_api


def build_forecast_summaries(db: Session) -> list[dict]:
    """
    Build one short outlook per enabled location for the list view.

    Unlike the detail view this keeps only the first few periods, so the page
    stays compact no matter how far out the provider forecasts.
    """
    locations = (
        db.query(Location)
        .filter(Location.enabled.is_(True))
        .order_by(Location.name)
        .all()
    )

    items = []
    for loc in locations:
        periods, source_api = _upcoming_periods(db, loc)
        items.append(
            {
                "location_name": loc.name,
                "slug": location_slug(loc),
                "source_api": source_api,
                "period_count": len(periods),
                "current": periods[0] if periods else None,
                "upcoming": periods[1 : SUMMARY_PERIOD_COUNT + 1],
            }
        )

    return items


def build_forecast_detail(db: Session, slug: str) -> dict | None:
    """
    Build the full period list for one location.

    Args:
        db: Database session
        slug: Location slug (or bare id)

    Returns:
        Detail dict, or None if there's no such location.
    """
    location = get_location_by_slug(db, slug)
    if location is None:
        return None

    periods, source_api = _upcoming_periods(db, location)

    return {
        "location_name": location.name,
        "slug": slug,
        "source_api": source_api,
        "periods": periods,
    }


@router.get("/forecast")
def forecast_page(request: Request, db: Session = Depends(get_db)):
    """Forecast overview: a short outlook per location, linking to each detail."""
    items = build_forecast_summaries(db)

    template = (
        "forecast/_content.html"
        if request.headers.get("HX-Request")
        else "forecast/list.html"
    )

    return templates.TemplateResponse(
        request,
        template,
        {
            "forecast_locations": items,
            "nav_active": "forecast",
        },
    )


@router.get("/forecast/{slug}")
def forecast_detail_page(slug: str, request: Request, db: Session = Depends(get_db)):
    """Every upcoming forecast period for a single location."""
    detail = build_forecast_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="Location not found")

    template = (
        "forecast/_detail_content.html"
        if request.headers.get("HX-Request")
        else "forecast/detail.html"
    )

    return templates.TemplateResponse(
        request,
        template,
        {
            "loc": detail,
            "nav_active": "forecast",
        },
    )
