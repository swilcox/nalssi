# Nalssi

Centralized weather data collection and distribution service. Fetches weather from multiple free APIs (NOAA, Open-Meteo, OpenWeatherMap) on a schedule, stores it, and distributes it to configurable output backends (Redis, InfluxDB) so other apps don't each make their own API calls.

See [README.md](README.md) for architecture, features, configuration, and the kurokku alert priority spec.

## Tech Stack

Python 3.11+ / FastAPI / SQLAlchemy / Alembic / APScheduler / httpx / Jinja2+HTMX. Managed with `uv`. Linted with `ruff`. Tested with `pytest`.

## Commands

```bash
# Setup
uv sync
uv run alembic upgrade head

# Run dev server
uv run uvicorn app.main:app --reload

# Tests
uv run pytest                   # all
uv run pytest -m unit           # unit only
uv run pytest -m integration    # integration only
uv run pytest --no-cov -q       # quick, no coverage

# Lint / format
uv run ruff check .
uv run ruff check --fix .
uv run ruff format .

# Docker
docker-compose up -d
```

## Conventions

- **TDD**: write failing tests first, then implement. Coverage target 80%+.
- **Flat layout**: `app/`, `tests/`, `pyproject.toml` at repo root (no `backend/` subdir).
- **Migrations**: use Alembic. Clean up false UUID↔NUMERIC type-change noise from autogenerate.
- **Don't fix unrelated lint**: pre-existing issues in `weather_collector.py`, `weather.py` route, and `test_weather_collector.py` are known — leave them unless the task targets them.
