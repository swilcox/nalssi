"""
Output backend configuration API routes.
"""

import json
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.backend_config import OutputBackendConfig
from app.schemas.backend_config import (
    BackendConfigCreate,
    BackendConfigResponse,
    BackendConfigUpdate,
)
from app.services.outputs.manager import _create_backend, _parse_json_field

router = APIRouter()
logger = structlog.get_logger()


def _config_to_response(config: OutputBackendConfig) -> dict:
    """Convert an OutputBackendConfig model to a response-friendly dict."""
    return {
        "id": config.id,
        "name": config.name,
        "backend_type": config.backend_type,
        "enabled": config.enabled,
        "connection_config": _parse_json_field(config.connection_config) or {},
        "format_type": config.format_type,
        "format_config": _parse_json_field(config.format_config),
        "location_filter": _parse_json_field(config.location_filter),
        "write_timeout": config.write_timeout,
        "retry_count": config.retry_count,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


@router.post(
    "/config/backends",
    response_model=BackendConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_backend_config(config: BackendConfigCreate, db: Session = Depends(get_db)):
    """Create a new output backend configuration."""
    db_config = OutputBackendConfig(
        name=config.name,
        backend_type=config.backend_type,
        enabled=config.enabled,
        connection_config=json.dumps(config.connection_config),
        format_type=config.format_type,
        format_config=json.dumps(config.format_config)
        if config.format_config
        else None,
        location_filter=json.dumps(config.location_filter)
        if config.location_filter
        else None,
        write_timeout=config.write_timeout,
        retry_count=config.retry_count,
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return _config_to_response(db_config)


@router.get("/config/backends", response_model=list[BackendConfigResponse])
def get_backend_configs(db: Session = Depends(get_db)):
    """Get all output backend configurations."""
    configs = db.query(OutputBackendConfig).all()
    return [_config_to_response(c) for c in configs]


@router.get("/config/backends/{config_id}", response_model=BackendConfigResponse)
def get_backend_config(config_id: UUID, db: Session = Depends(get_db)):
    """Get a specific backend configuration."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend config {config_id} not found",
        )
    return _config_to_response(config)


@router.put("/config/backends/{config_id}", response_model=BackendConfigResponse)
def update_backend_config(
    config_id: UUID,
    config_update: BackendConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update a backend configuration."""
    db_config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend config {config_id} not found",
        )

    update_data = config_update.model_dump(exclude_unset=True)

    # Serialize JSON fields
    json_fields = ["connection_config", "format_config", "location_filter"]
    for field_name in json_fields:
        if field_name in update_data:
            value = update_data[field_name]
            update_data[field_name] = json.dumps(value) if value is not None else None

    for field_name, value in update_data.items():
        setattr(db_config, field_name, value)

    db.commit()
    db.refresh(db_config)
    return _config_to_response(db_config)


@router.delete("/config/backends/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backend_config(config_id: UUID, db: Session = Depends(get_db)):
    """Delete a backend configuration."""
    db_config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend config {config_id} not found",
        )

    db.delete(db_config)
    db.commit()


@router.post(
    "/config/backends/{config_id}/test",
    response_model=dict,
)
async def test_backend_connection(config_id: UUID, db: Session = Depends(get_db)):
    """Test connectivity to a backend."""
    db_config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend config {config_id} not found",
        )

    backend = _create_backend(db_config)
    if not backend:
        return {
            "success": False,
            "message": f"Unsupported backend type: {db_config.backend_type}",
        }

    try:
        success = await backend.test_connection()
        return {
            "success": success,
            "message": "Connection successful" if success else "Connection failed",
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
    finally:
        await backend.close()
