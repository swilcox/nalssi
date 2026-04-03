"""
Logging configuration for the application.

Uses structlog for structured logging with JSON output in production
and colored console output in development.
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure application logging with structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: Whether to use JSON formatting (True for production)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    if json_logs:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # Processors for structlog's own loggers (PrintLoggerFactory)
    # Note: add_logger_name is stdlib-only, so it's excluded here.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging for third-party libraries (uvicorn, sqlalchemy, etc.)
    # Note: add_logger_name doesn't work in ProcessorFormatter (logger arg is None).
    # Extract logger name from the stdlib LogRecord via _record instead.
    def add_logger_name_from_record(
        logger: object, method_name: str, event_dict: dict
    ) -> dict:
        record = event_dict.get("_record")
        if record is not None:
            event_dict["logger"] = record.name
        return event_dict

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            add_logger_name_from_record,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ExtraAdder(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Reduce noise from third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)


def unify_uvicorn_logging() -> None:
    """
    Override uvicorn's loggers to use our root handler/formatter.

    Must be called AFTER uvicorn has started (e.g. in the FastAPI lifespan),
    because uvicorn re-configures its own loggers during startup, overwriting
    any earlier changes.
    """
    root_handler = (
        logging.getLogger().handlers[0] if logging.getLogger().handlers else None
    )
    if root_handler is None:
        return

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [root_handler]
        uv_logger.propagate = False
