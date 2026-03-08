"""
Output backend configuration page routes.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.backend_config import OutputBackendConfig
from app.models.location import Location
from app.services.outputs.manager import _create_backend
from app.services.outputs.redis_backend import FORMAT_TRANSFORMS
from app.templating import templates

router = APIRouter()

FORMAT_TYPE_CHOICES = [("", "(none)")] + [(key, key) for key in FORMAT_TRANSFORMS]


def _get_locations(db: Session) -> list[dict]:
    """Get all locations as simple dicts for the filter dropdown."""
    locations = db.query(Location).order_by(Location.name).all()
    return [{"slug": loc.slug, "name": loc.name} for loc in locations]


def _backend_display(config: OutputBackendConfig) -> dict:
    """Build a display dict for a backend config row."""
    # Parse location filter to extract mode and selected slugs
    filter_mode = "all"
    filter_slugs = []
    raw_filter = config.location_filter
    if raw_filter:
        try:
            parsed = json.loads(raw_filter)
            if "include" in parsed:
                filter_mode = "include"
                filter_slugs = parsed["include"]
            elif "exclude" in parsed:
                filter_mode = "exclude"
                filter_slugs = parsed["exclude"]
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "id": config.id,
        "name": config.name,
        "backend_type": config.backend_type,
        "enabled": config.enabled,
        "connection_config": config.connection_config or "{}",
        "format_type": config.format_type,
        "format_config": config.format_config or "",
        "location_filter": raw_filter or "",
        "filter_mode": filter_mode,
        "filter_slugs": filter_slugs,
        "write_timeout": config.write_timeout,
        "retry_count": config.retry_count,
    }


def _try_parse_json(value: str, field_name: str) -> tuple[str | None, str | None]:
    """Try to parse a JSON string. Returns (json_str, error)."""
    value = value.strip()
    if not value:
        return None, None
    try:
        parsed = json.loads(value)
        return json.dumps(parsed), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {field_name}: {e}"


def _build_location_filter(filter_mode: str, filter_locations: list[str]) -> str | None:
    """Build location_filter JSON from form values."""
    if filter_mode == "all" or not filter_locations:
        return None
    if filter_mode == "include":
        return json.dumps({"include": filter_locations})
    if filter_mode == "exclude":
        return json.dumps({"exclude": filter_locations})
    return None


def _common_context(db: Session) -> dict:
    """Build context vars shared by all backend templates."""
    return {
        "format_types": FORMAT_TYPE_CHOICES,
        "locations": _get_locations(db),
    }


@router.get("/backends")
def backends_list(request: Request, db: Session = Depends(get_db)):
    """Backends list page."""
    configs = db.query(OutputBackendConfig).order_by(OutputBackendConfig.name).all()
    backends = [_backend_display(c) for c in configs]
    return templates.TemplateResponse(
        "backends/list.html",
        {"request": request, "backends": backends, **_common_context(db)},
    )


@router.post("/backends")
def create_backend_config(
    request: Request,
    name: str = Form(),
    backend_type: str = Form(),
    connection_config: str = Form(),
    format_type: str = Form(""),
    format_config: str = Form(""),
    filter_mode: str = Form("all"),
    filter_locations: list[str] = Form([]),
    write_timeout: int = Form(10),
    retry_count: int = Form(1),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    """Create a new backend config, return row fragment."""
    errors = []
    if not name.strip():
        errors.append("Name is required.")

    conn_json, conn_err = _try_parse_json(connection_config, "connection_config")
    if conn_err:
        errors.append(conn_err)
    elif not conn_json:
        errors.append("Connection config is required.")

    fmt_json, fmt_err = _try_parse_json(format_config, "format_config")
    if fmt_err:
        errors.append(fmt_err)

    if errors:
        error_html = (
            '<div class="error-message"><small>' + "; ".join(errors) + "</small></div>"
        )
        return Response(
            content=error_html,
            headers={
                "HX-Retarget": "#add-backend-errors",
                "HX-Reswap": "innerHTML",
            },
        )

    location_filter = _build_location_filter(filter_mode, filter_locations)

    config = OutputBackendConfig(
        name=name.strip(),
        backend_type=backend_type.strip(),
        enabled=enabled == "on",
        connection_config=conn_json,
        format_type=format_type.strip() or None,
        format_config=fmt_json,
        location_filter=location_filter,
        write_timeout=write_timeout,
        retry_count=retry_count,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    return templates.TemplateResponse(
        "backends/_row.html",
        {
            "request": request,
            "backend": _backend_display(config),
            **_common_context(db),
        },
        headers={"HX-Trigger": "clearErrors"},
    )


@router.get("/backends/{config_id}/edit")
def edit_backend_form(
    request: Request,
    config_id: UUID,
    db: Session = Depends(get_db),
):
    """Return inline edit form for a backend config."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        return Response(content="Backend not found", status_code=404)
    return templates.TemplateResponse(
        "backends/_form.html",
        {
            "request": request,
            "backend": _backend_display(config),
            **_common_context(db),
        },
    )


@router.get("/backends/{config_id}/row")
def backend_row(
    request: Request,
    config_id: UUID,
    db: Session = Depends(get_db),
):
    """Return read-only row for a backend config (cancel edit)."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        return Response(content="Backend not found", status_code=404)
    return templates.TemplateResponse(
        "backends/_row.html",
        {
            "request": request,
            "backend": _backend_display(config),
            **_common_context(db),
        },
    )


@router.put("/backends/{config_id}")
def update_backend_config(
    request: Request,
    config_id: UUID,
    name: str = Form(),
    backend_type: str = Form(),
    connection_config: str = Form(),
    format_type: str = Form(""),
    format_config: str = Form(""),
    filter_mode: str = Form("all"),
    filter_locations: list[str] = Form([]),
    write_timeout: int = Form(10),
    retry_count: int = Form(1),
    enabled: str = Form("off"),
    db: Session = Depends(get_db),
):
    """Update a backend config, return updated row fragment."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        return Response(content="Backend not found", status_code=404)

    errors = []
    if not name.strip():
        errors.append("Name is required.")

    conn_json, conn_err = _try_parse_json(connection_config, "connection_config")
    if conn_err:
        errors.append(conn_err)
    elif not conn_json:
        errors.append("Connection config is required.")

    fmt_json, fmt_err = _try_parse_json(format_config, "format_config")
    if fmt_err:
        errors.append(fmt_err)

    if errors:
        backend_data = _backend_display(config)
        return templates.TemplateResponse(
            "backends/_form.html",
            {
                "request": request,
                "backend": backend_data,
                "error": "; ".join(errors),
                **_common_context(db),
            },
        )

    location_filter = _build_location_filter(filter_mode, filter_locations)

    config.name = name.strip()
    config.backend_type = backend_type.strip()
    config.enabled = enabled == "on"
    config.connection_config = conn_json
    config.format_type = format_type.strip() or None
    config.format_config = fmt_json
    config.location_filter = location_filter
    config.write_timeout = write_timeout
    config.retry_count = retry_count

    db.commit()
    db.refresh(config)

    return templates.TemplateResponse(
        "backends/_row.html",
        {
            "request": request,
            "backend": _backend_display(config),
            **_common_context(db),
        },
    )


@router.delete("/backends/{config_id}")
def delete_backend_config(
    config_id: UUID,
    db: Session = Depends(get_db),
):
    """Delete a backend config, return empty response to remove row."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        return Response(content="Backend not found", status_code=404)

    db.delete(config)
    db.commit()
    return Response(content="")


@router.post("/backends/{config_id}/test")
async def test_backend_connection(
    config_id: UUID,
    db: Session = Depends(get_db),
):
    """Test backend connection, return badge fragment."""
    config = (
        db.query(OutputBackendConfig)
        .filter(OutputBackendConfig.id == config_id)
        .first()
    )
    if not config:
        return Response(content="Backend not found", status_code=404)

    backend = _create_backend(config)
    if not backend:
        return Response(
            content=f'<span class="badge badge-error">Unsupported: {config.backend_type}</span>'
        )

    try:
        success = await backend.test_connection()
        if success:
            return Response(
                content='<span class="badge badge-success">Connected</span>'
            )
        else:
            return Response(content='<span class="badge badge-error">Failed</span>')
    except Exception as e:
        return Response(content=f'<span class="badge badge-error">{e}</span>')
    finally:
        await backend.close()
