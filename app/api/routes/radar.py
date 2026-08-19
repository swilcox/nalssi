"""
Radar image serving routes.

Serves the PNG files written by the radar collector. These are plain files on
disk rather than a mounted static directory so that paths can be validated,
missing frames return a proper 404, and cache headers can be set per resource.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.location import Location
from app.services.collectors.radar_collector import (
    basemap_name,
    key_for_location,
    radar_dir,
    storage_root,
)
from app.services.imagery.radar import BASEMAP_LAYERS

router = APIRouter()

# Frames are immutable once written: a given location/timestamp always renders
# the same image, so they can be cached indefinitely.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def _get_location(db: Session, slug: str) -> Location:
    """Look up an enabled location by slug, or 404."""
    location = db.query(Location).filter(Location.slug == slug).first()
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def _safe_file(path: Path) -> FileResponse:
    """
    Serve a file, ensuring it resolves inside the radar storage directory.

    Guards against a crafted slug or filename escaping the storage root.
    """
    root = storage_root().resolve()
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(
        resolved,
        media_type="image/png",
        headers={"Cache-Control": IMMUTABLE_CACHE},
    )


@router.get("/radar/{slug}/basemap/{kind}.png")
def radar_basemap(slug: str, kind: str, db: Session = Depends(get_db)):
    """
    Serve one band of a location's basemap.

    Bands (water, counties, admin) are stored and served separately so the
    viewer can style each one differently.
    """
    location = _get_location(db, slug)

    resolved = key_for_location(location)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Location has no radar coverage")
    key, _source, bbox = resolved

    layer = next((band for band in BASEMAP_LAYERS if band.kind == kind), None)
    if layer is None:
        raise HTTPException(status_code=404, detail="Unknown basemap band")

    return _safe_file(radar_dir(key) / basemap_name(bbox, layer))


@router.get("/radar/{slug}/frames/{epoch}.png")
def radar_frame(slug: str, epoch: int, db: Session = Depends(get_db)):
    """Serve a single stored radar frame by its epoch-second timestamp."""
    location = _get_location(db, slug)

    resolved = key_for_location(location)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Location has no radar coverage")

    return _safe_file(radar_dir(resolved[0]) / f"{epoch}.png")
