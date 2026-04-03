"""
Location management page routes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.utils import slugify
from app.models.location import Location
from app.templating import templates

router = APIRouter()


@router.get("/locations")
def locations_list(request: Request, db: Session = Depends(get_db)):
    """Locations list page."""
    locations = db.query(Location).order_by(Location.name).all()
    return templates.TemplateResponse(
        request,
        "locations/list.html",
        {"locations": locations, "nav_active": "locations"},
    )


@router.post("/locations")
def create_location(
    request: Request,
    name: str = Form(),
    latitude: float = Form(),
    longitude: float = Form(),
    country_code: str = Form(),
    timezone: str = Form(""),
    collection_interval: int = Form(300),
    preferred_api: str = Form(""),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    """Create a new location, return row fragment."""
    # Validate
    errors = []
    if not name.strip():
        errors.append("Name is required.")
    if latitude < -90 or latitude > 90:
        errors.append("Latitude must be between -90 and 90.")
    if longitude < -180 or longitude > 180:
        errors.append("Longitude must be between -180 and 180.")
    if collection_interval < 1:
        errors.append("Collection interval must be positive.")

    if errors:
        error_html = (
            '<div class="error-message"><small>' + "; ".join(errors) + "</small></div>"
        )
        return Response(
            content=error_html,
            headers={
                "HX-Retarget": "#add-location-errors",
                "HX-Reswap": "innerHTML",
            },
        )

    # Generate slug
    base_slug = slugify(name)
    slug = base_slug
    suffix = 2
    while db.query(Location).filter(Location.slug == slug).first():
        slug = f"{base_slug}_{suffix}"
        suffix += 1

    location = Location(
        name=name.strip(),
        slug=slug,
        latitude=latitude,
        longitude=longitude,
        country_code=country_code.upper().strip(),
        timezone=timezone.strip() or None,
        collection_interval=collection_interval,
        preferred_api=preferred_api.strip() or None,
        enabled=enabled == "on",
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    return templates.TemplateResponse(
        request,
        "locations/_row.html",
        {"location": location},
        headers={"HX-Trigger": "clearErrors"},
    )


@router.get("/locations/{location_id}/edit")
def edit_location_form(
    request: Request,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """Return inline edit form for a location."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        return Response(content="Location not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "locations/_form.html",
        {"location": location},
    )


@router.get("/locations/{location_id}/row")
def location_row(
    request: Request,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """Return read-only row for a location (cancel edit)."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        return Response(content="Location not found", status_code=404)
    return templates.TemplateResponse(
        request,
        "locations/_row.html",
        {"location": location},
    )


@router.put("/locations/{location_id}")
def update_location(
    request: Request,
    location_id: UUID,
    name: str = Form(),
    latitude: float = Form(),
    longitude: float = Form(),
    country_code: str = Form(),
    timezone: str = Form(""),
    collection_interval: int = Form(300),
    preferred_api: str = Form(""),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    """Update a location, return updated row fragment."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        return Response(content="Location not found", status_code=404)

    # Validate
    errors = []
    if not name.strip():
        errors.append("Name is required.")
    if latitude < -90 or latitude > 90:
        errors.append("Latitude must be between -90 and 90.")
    if longitude < -180 or longitude > 180:
        errors.append("Longitude must be between -180 and 180.")
    if collection_interval < 1:
        errors.append("Collection interval must be positive.")

    if errors:
        return templates.TemplateResponse(
            request,
            "locations/_form.html",
            {"location": location, "error": "; ".join(errors)},
        )

    location.name = name.strip()
    location.latitude = latitude
    location.longitude = longitude
    location.country_code = country_code.upper().strip()
    location.timezone = timezone.strip() or None
    location.collection_interval = collection_interval
    location.preferred_api = preferred_api.strip() or None
    location.enabled = enabled == "on"

    db.commit()
    db.refresh(location)

    return templates.TemplateResponse(
        request,
        "locations/_row.html",
        {"location": location},
    )


@router.delete("/locations/{location_id}")
def delete_location(
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete a location, return empty response to remove row."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        return Response(content="Location not found", status_code=404)

    db.delete(location)
    db.commit()
    return Response(content="")
