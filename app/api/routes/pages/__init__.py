"""
Server-rendered HTML page routes using htmx + Pico CSS.
"""

import uuid

from sqlalchemy.orm import Session

from app.models.location import Location


def location_slug(location: Location) -> str:
    """
    Get the URL segment identifying a location.

    Locations aren't guaranteed to have a slug, so they fall back to their id.
    """
    return location.slug or str(location.id)


def get_location_by_slug(db: Session, slug: str) -> Location | None:
    """
    Look up a location by its URL segment.

    Accepts either a slug or a bare id, mirroring what ``location_slug``
    produces, so detail pages can resolve whatever the list view linked to.

    Args:
        db: Database session
        slug: Slug or id from the URL

    Returns:
        The Location, or None if there's no match.
    """
    location = db.query(Location).filter(Location.slug == slug).first()
    if location is not None:
        return location

    try:
        location_id = uuid.UUID(slug)
    except ValueError:
        return None

    return db.query(Location).filter(Location.id == location_id).first()
