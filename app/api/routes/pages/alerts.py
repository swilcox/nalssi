"""
Alerts page route.
"""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.alert import Alert
from app.models.location import Location
from app.templating import templates

router = APIRouter()


def build_alert_items(db: Session) -> list[dict]:
    """Build the list of active alert items for display."""
    now = datetime.now(UTC)

    alerts = (
        db.query(Alert)
        .join(Location)
        .filter(Alert.expires > now)
        .order_by(Alert.severity, Alert.effective.desc())
        .all()
    )

    items = []
    for alert in alerts:
        areas = []
        if alert.areas:
            try:
                areas = json.loads(alert.areas)
            except (json.JSONDecodeError, TypeError):
                areas = []

        items.append(
            {
                "id": str(alert.id),
                "location_name": alert.location.name if alert.location else "Unknown",
                "event": alert.event,
                "headline": alert.headline,
                "severity": alert.severity,
                "urgency": alert.urgency,
                "certainty": alert.certainty,
                "category": alert.category,
                "response_type": alert.response_type,
                "sender_name": alert.sender_name,
                "status": alert.status,
                "message_type": alert.message_type,
                "effective": alert.effective.strftime("%Y-%m-%d %H:%M UTC")
                if alert.effective
                else "",
                "expires": alert.expires.strftime("%Y-%m-%d %H:%M UTC")
                if alert.expires
                else "",
                "onset": alert.onset.strftime("%Y-%m-%d %H:%M UTC")
                if alert.onset
                else None,
                "ends": alert.ends.strftime("%Y-%m-%d %H:%M UTC")
                if alert.ends
                else None,
                "areas": areas,
                "description": alert.description,
                "instruction": alert.instruction,
                "source_api": alert.source_api,
            }
        )

    return items


@router.get("/alerts")
def alerts_page(request: Request, db: Session = Depends(get_db)):
    """Active weather alerts across all locations."""
    items = build_alert_items(db)

    template = (
        "alerts/_content.html"
        if request.headers.get("HX-Request")
        else "alerts/list.html"
    )

    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "alerts": items,
            "alert_count": len(items),
            "nav_active": "alerts",
        },
    )
