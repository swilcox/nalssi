"""
System-level API routes (health check, metrics, etc.).
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import settings
from app.schemas.weather import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns the service health status, version, and current timestamp.
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        timestamp=datetime.now(UTC).isoformat(),
    )
