# Nalssi

Nalssi (날씨, Korean for "weather") is a centralized weather data collection and distribution service. It fetches weather data from multiple free APIs on a schedule, stores it locally, and distributes it to configurable output backends — so your other applications can consume weather data without each making their own API calls.

## How It Works

```mermaid
flowchart LR
    subgraph apis["Weather APIs"]
        noaa["NOAA"]
        openmeteo["Open-Meteo"]
        openweather["OpenWeatherMap"]
    end

    subgraph nalssi["Nalssi"]
        scheduler["Scheduler"]
        collector["Collector"]
        db[("SQLite/PG")]
        api["REST API"]
        webui["Web UI"]
    end

    subgraph outputs["Output Backends"]
        redis["Redis"]
        influxdb["InfluxDB"]
    end

    scheduler -->|triggers| collector
    collector --> noaa & openmeteo & openweather
    collector -->|store| db
    collector -->|distribute| redis & influxdb
    db --- api
    api --- webui
```

**Collector** runs on a configurable interval (default: 5 min), selects the right API per location (NOAA for US, Open-Meteo for international), normalizes responses into a common format, stores them, and pushes to any enabled output backends.

## Features

- **Multi-API support** — NOAA Weather.gov, Open-Meteo, OpenWeatherMap with automatic selection and fallback
- **Weather alerts** — Collects and stores warnings/watches with upsert deduplication
- **Output backends** — Redis (with pluggable format transforms) and InfluxDB, with more planned
- **REST API** — Full CRUD for locations, weather data, alerts, and backend configuration
- **Web UI** — HTMX-based dashboard for managing locations, backends, and viewing weather data
- **Scheduled collection** — Background APScheduler with per-location intervals
- **Docker ready** — Single `docker-compose up` to run everything

## Quick Start

```bash
# Clone and start with Docker
git clone https://github.com/swilcox/nalssi.git
cd nalssi
docker-compose up -d

# Or run locally with uv
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API and web UI will be available at `http://localhost:8000`.

## Supported Weather APIs

| API | Coverage | Cost | API Key Required |
|-----|----------|------|:---:|
| NOAA Weather.gov | US | Free | No |
| Open-Meteo | Global | Free (non-commercial) | No |
| OpenWeatherMap | Global | Free tier | Yes |

## API Documentation

Once running, visit:
- Interactive API docs: `http://localhost:8000/docs`
- Alternative API docs: `http://localhost:8000/redoc`

## Testing

```bash
uv run pytest                   # Run all tests
uv run pytest -m unit           # Unit tests only
uv run pytest -m integration    # Integration tests only
uv run pytest --no-cov -q       # Quick run without coverage
```

## Code Quality

```bash
uv run ruff check .             # Lint
uv run ruff format .            # Format
```

## Configuration

Copy `.env.example` to `.env` and edit as needed. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./nalssi.db` | Database connection |
| `DEFAULT_COLLECTION_INTERVAL` | `300` | Seconds between collections |
| `ENABLE_SCHEDULER` | `true` | Enable/disable background collection |
| `OPENWEATHER_API_KEY` | | Required for OpenWeatherMap |
| `REDIS_URL` | | Redis backend connection |
| `INFLUXDB_URL` | | InfluxDB backend connection |

## Project Structure

```
nalssi/
├── app/
│   ├── api/routes/             # REST API + page routes
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/
│   │   ├── collectors/         # Weather collection
│   │   ├── weather_apis/       # API clients (NOAA, Open-Meteo, OpenWeather)
│   │   ├── outputs/            # Output backends (Redis, InfluxDB)
│   │   ├── broadcast.py        # WebSocket connection manager
│   │   └── scheduler.py        # APScheduler setup
│   ├── templates/              # Jinja2 + HTMX templates
│   ├── config.py               # Pydantic settings
│   ├── database.py             # SQLAlchemy setup
│   └── main.py                 # FastAPI application
├── tests/
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── fixtures/               # Test fixtures (API responses)
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── uv.lock
```

## Tech Stack

- **Python 3.11+** / **FastAPI** / **SQLAlchemy** / **Alembic**
- **APScheduler** for background collection
- **httpx** for async HTTP
- **Jinja2 + HTMX** for web UI with live WebSocket updates
- **Docker** for deployment
- **uv** for dependency management
- **ruff** for linting/formatting, **pytest** for testing

## License

TBD
