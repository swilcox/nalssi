"""
Main FastAPI application for nalssi weather service.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import backends, locations, system, weather, ws
from app.api.routes.pages import alerts as page_alerts
from app.api.routes.pages import backends as page_backends
from app.api.routes.pages import dashboard as page_dashboard
from app.api.routes.pages import locations as page_locations
from app.api.routes.pages import system as page_system
from app.config import settings
from app.logging_config import setup_logging, unify_uvicorn_logging
from app.services.scheduler import get_scheduler

# Initialize logging
setup_logging(log_level=settings.LOG_LEVEL, json_logs=settings.JSON_LOGS)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Override uvicorn's loggers now that uvicorn has finished its own setup
    unify_uvicorn_logging()

    # Startup
    logger.info(
        "Starting nalssi weather service",
        extra={
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "log_level": settings.LOG_LEVEL,
            "json_logs": settings.JSON_LOGS,
        },
    )

    # Start the scheduler if enabled
    scheduler = None
    if settings.ENABLE_SCHEDULER:
        scheduler = get_scheduler()
        scheduler.start()

    yield

    # Shutdown
    logger.info("Shutting down nalssi weather service")
    if scheduler:
        scheduler.shutdown()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Weather data collection and distribution service",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(system.router, tags=["System"])
app.include_router(locations.router, prefix="/api/v1", tags=["Locations"])
app.include_router(weather.router, prefix="/api/v1", tags=["Weather"])
app.include_router(backends.router, prefix="/api/v1", tags=["Backends"])

# Include WebSocket router
app.include_router(ws.router)

# Include page routers (server-rendered HTML with htmx)
app.include_router(page_dashboard.router, tags=["Pages"])
app.include_router(page_locations.router, tags=["Pages"])
app.include_router(page_backends.router, tags=["Pages"])
app.include_router(page_alerts.router, tags=["Pages"])
app.include_router(page_system.router, tags=["Pages"])
