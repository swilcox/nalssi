# Multi-stage build for nalssi backend service
# Stage 1: Build stage with uv for dependency management
FROM python:3.11-slim as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml .
COPY uv.lock .

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Stage 2: Runtime stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy uv from builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app ./app
COPY alembic.ini .
COPY pyproject.toml .
COPY uv.lock .

# Create directory for data (logs, etc.)
RUN mkdir -p /app/data

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    JSON_LOGS=true

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Create entrypoint script
RUN echo '#!/bin/sh\n\
set -e\n\
echo "Running database migrations..."\n\
uv run alembic upgrade head\n\
echo "Starting FastAPI application..."\n\
exec uv run python -m app.server\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Run entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
