"""
Uvicorn entry point with unified logging.

Launches uvicorn with log_config=None so that all logging
(including uvicorn access/error logs) uses our shared formatter
configured in app.logging_config.
"""

import sys

import uvicorn

from app.config import settings


def main() -> None:
    """Run the uvicorn server."""
    # Pass through any CLI-style flags
    reload = "--reload" in sys.argv

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=reload,
        log_config=None,  # Disable uvicorn's default logging; we configure our own
    )


if __name__ == "__main__":
    main()
