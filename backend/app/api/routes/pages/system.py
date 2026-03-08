"""
System status page route.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.models.alert import Alert
from app.models.backend_config import OutputBackendConfig
from app.models.location import Location
from app.models.weather import WeatherData
from app.templating import templates

router = APIRouter()


def build_system_stats(db: Session) -> dict:
    """Build system stat counts."""
    now = datetime.now(UTC)
    return {
        "location_count": db.query(func.count(Location.id)).scalar(),
        "backend_count": db.query(func.count(OutputBackendConfig.id)).scalar(),
        "active_alert_count": (
            db.query(func.count(Alert.id)).filter(Alert.expires > now).scalar()
        ),
    }


def build_last_collections(db: Session) -> list[dict]:
    """Build last collection data per location."""
    locations = db.query(Location).order_by(Location.name).all()
    last_collections = []
    for loc in locations:
        latest = (
            db.query(WeatherData)
            .filter(WeatherData.location_id == loc.id)
            .order_by(desc(WeatherData.timestamp))
            .first()
        )
        last_collections.append(
            {
                "location_name": loc.name,
                "timestamp": latest.timestamp.strftime("%Y-%m-%d %H:%M UTC")
                if latest and latest.timestamp
                else None,
                "source_api": latest.source_api if latest else None,
                "temperature": latest.temperature if latest else None,
                "temperature_f": latest.temperature_fahrenheit
                if latest and latest.temperature_fahrenheit
                else (
                    latest.temperature * 9 / 5 + 32
                    if latest and latest.temperature is not None
                    else None
                ),
            }
        )
    return last_collections


@router.get("/system")
def system_status(request: Request, db: Session = Depends(get_db)):
    """System status page."""
    stats = build_system_stats(db)

    # Scheduler jobs
    scheduler_jobs = []
    try:
        from app.services.scheduler import get_scheduler

        scheduler = get_scheduler()
        scheduler_jobs = scheduler.get_jobs()
    except Exception:
        pass

    last_collections = build_last_collections(db)

    return templates.TemplateResponse(
        "system/status.html",
        {
            "request": request,
            "version": settings.APP_VERSION,
            **stats,
            "scheduler_jobs": scheduler_jobs,
            "last_collections": last_collections,
        },
    )
