"""
Location management API routes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.utils import slugify
from app.models.location import Location
from app.schemas.location import LocationCreate, LocationResponse, LocationUpdate

router = APIRouter()


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_location(location: LocationCreate, db: Session = Depends(get_db)):
    """
    Create a new location for weather monitoring.

    Args:
        location: Location data
        db: Database session

    Returns:
        Created location
    """
    data = location.model_dump()
    # Auto-generate slug from name if not provided
    if not data.get("slug"):
        base_slug = slugify(data["name"])
        slug = base_slug
        # Handle duplicate slugs by appending a numeric suffix
        suffix = 2
        while db.query(Location).filter(Location.slug == slug).first():
            slug = f"{base_slug}_{suffix}"
            suffix += 1
        data["slug"] = slug
    db_location = Location(**data)
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location


@router.get("/locations", response_model=list[LocationResponse])
def get_locations(db: Session = Depends(get_db)):
    """
    Get all locations.

    Args:
        db: Database session

    Returns:
        List of all locations
    """
    locations = db.query(Location).all()
    return locations


@router.get("/locations/{location_id}", response_model=LocationResponse)
def get_location(location_id: UUID, db: Session = Depends(get_db)):
    """
    Get a specific location by ID.

    Args:
        location_id: Location UUID
        db: Database session

    Returns:
        Location details

    Raises:
        HTTPException: If location not found
    """
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )
    return location


@router.put("/locations/{location_id}", response_model=LocationResponse)
def update_location(
    location_id: UUID, location_update: LocationUpdate, db: Session = Depends(get_db)
):
    """
    Update a location.

    Args:
        location_id: Location UUID
        location_update: Fields to update
        db: Database session

    Returns:
        Updated location

    Raises:
        HTTPException: If location not found
    """
    db_location = db.query(Location).filter(Location.id == location_id).first()
    if not db_location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )

    # Update only provided fields
    update_data = location_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_location, field, value)

    db.commit()
    db.refresh(db_location)
    return db_location


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(location_id: UUID, db: Session = Depends(get_db)):
    """
    Delete a location.

    Args:
        location_id: Location UUID
        db: Database session

    Raises:
        HTTPException: If location not found
    """
    db_location = db.query(Location).filter(Location.id == location_id).first()
    if not db_location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )

    db.delete(db_location)
    db.commit()
