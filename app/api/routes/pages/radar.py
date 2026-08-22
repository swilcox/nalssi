"""
Radar page routes.

``/radar`` lists every location with a still of its most recent frame;
``/radar/{slug}`` is the per-location detail view with the animated loop. The
split keeps the list cheap — one image per location instead of a full two-hour
loop each — and gives the detail view room to grow.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.pages import get_location_by_slug, location_slug
from app.config import settings
from app.models.location import Location
from app.models.radar_frame import RadarFrame
from app.services.imagery.radar import BASEMAP_LAYERS, source_for
from app.templating import templates

router = APIRouter()


def build_range_rings(span_km: float) -> list[dict]:
    """
    Build range ring geometry for a view of the given span.

    Radii are expressed in the viewer's 100x100 SVG viewBox, where the full
    image width is the view span. Because the location sits at the exact center
    of the image by construction, a ring is simply a circle at 50,50.

    Rings wider than half the span are dropped — they'd fall outside the image
    edges entirely.

    Args:
        span_km: Width of the view in kilometres

    Returns:
        List of {"km", "radius"} dicts, nearest ring first.
    """
    rings = []
    for km in settings.radar_range_rings:
        if km > span_km / 2:
            continue
        rings.append({"km": km, "radius": 100.0 * km / span_km})
    return rings


def _basemap_bands(slug: str) -> list[dict]:
    """Build the basemap band URLs for a location, bottom band first."""
    return [
        {"kind": band.kind, "url": f"/radar/{slug}/basemap/{band.kind}.png"}
        for band in BASEMAP_LAYERS
    ]


def _frame_url(slug: str, frame: RadarFrame) -> str:
    """Build the served URL for a stored frame."""
    return f"/radar/{slug}/frames/{frame.epoch}.png"


def build_radar_summaries(db: Session) -> list[dict]:
    """
    Build one summary per enabled location for the list view.

    Only the newest frame is loaded per location, so the list stays a handful of
    images regardless of how much history is retained.
    """
    locations = (
        db.query(Location)
        .filter(Location.enabled.is_(True))
        .order_by(Location.name)
        .all()
    )

    items = []
    for loc in locations:
        slug = location_slug(loc)
        covered = source_for(loc.latitude, loc.longitude, loc.country_code) is not None

        latest = None
        frame_count = 0
        if covered:
            frame_count = (
                db.query(RadarFrame).filter(RadarFrame.location_id == loc.id).count()
            )
            latest = (
                db.query(RadarFrame)
                .filter(RadarFrame.location_id == loc.id)
                .order_by(RadarFrame.frame_time.desc())
                .first()
            )

        items.append(
            {
                "name": loc.name,
                "slug": slug,
                "covered": covered,
                "frame_count": frame_count,
                "span_km": settings.RADAR_VIEW_SPAN_KM,
                "basemap_bands": _basemap_bands(slug),
                "latest": (
                    {
                        "url": _frame_url(slug, latest),
                        "timestamp": latest.frame_time_utc.isoformat(),
                    }
                    if latest
                    else None
                ),
            }
        )

    return items


def build_radar_detail(db: Session, slug: str) -> dict | None:
    """
    Build the full animated view for one location.

    Args:
        db: Database session
        slug: Location slug (or bare id, for locations without a slug)

    Returns:
        Detail dict, or None if no such location.
    """
    location = get_location_by_slug(db, slug)
    if location is None:
        return None

    source = source_for(location.latitude, location.longitude, location.country_code)
    covered = source is not None
    frames: list[RadarFrame] = []
    if covered:
        frames = (
            db.query(RadarFrame)
            .filter(RadarFrame.location_id == location.id)
            .order_by(RadarFrame.frame_time)
            .all()
        )

    return {
        "name": location.name,
        "slug": slug,
        "covered": covered,
        "provider": source.provider if source else None,
        "enabled": location.enabled,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "span_km": settings.RADAR_VIEW_SPAN_KM,
        "rings": build_range_rings(settings.RADAR_VIEW_SPAN_KM),
        "basemap_bands": _basemap_bands(slug),
        "frames": [
            {
                "url": _frame_url(slug, f),
                "timestamp": f.frame_time_utc.isoformat(),
            }
            for f in frames
        ],
    }


@router.get("/radar")
def radar_page(request: Request, db: Session = Depends(get_db)):
    """Radar overview: latest frame per location, linking to each detail view."""
    items = build_radar_summaries(db)

    template = (
        "radar/_content.html"
        if request.headers.get("HX-Request")
        else "radar/list.html"
    )

    return templates.TemplateResponse(
        request,
        template,
        {
            "radar_locations": items,
            "nav_active": "radar",
        },
    )


@router.get("/radar/{slug}")
def radar_detail_page(slug: str, request: Request, db: Session = Depends(get_db)):
    """Animated radar loop for a single location."""
    detail = build_radar_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="Location not found")

    template = (
        "radar/_detail_content.html"
        if request.headers.get("HX-Request")
        else "radar/detail.html"
    )

    return templates.TemplateResponse(
        request,
        template,
        {
            "loc": detail,
            "nav_active": "radar",
        },
    )
