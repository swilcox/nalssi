# Nalssi Backend

Weather data collection and distribution service. Nalssi centralizes weather API calls so multiple applications can consume weather data without each making their own API requests, reducing costs and API rate limit concerns.

## Architecture

```mermaid
flowchart TB
    subgraph scheduler["Scheduler (APScheduler)"]
        direction LR
        tick["Every N seconds<br/>(default: 300s)"]
    end

    subgraph collector["Weather Collector"]
        direction TB
        select["Select API client<br/>per location"]
        normalize["Normalize response<br/>to common format"]
        store["Store in database"]
        distribute["Distribute to<br/>output backends"]
        select --> normalize --> store --> distribute
    end

    subgraph apis["Weather APIs"]
        noaa["NOAA Weather.gov<br/><i>US locations, free</i>"]
        openmeteo["Open-Meteo<br/><i>Global, free non-commercial</i>"]
        openweather["OpenWeatherMap<br/><i>Global, API key required</i>"]
    end

    subgraph db["Configuration & Storage (SQLite / PostgreSQL)"]
        locations[("locations<br/><i>enabled locations</i>")]
        weather_data[("weather_data<br/><i>observations</i>")]
        alerts_table[("alerts<br/><i>warnings & watches</i>")]
        backend_config[("output_backend_config<br/><i>backend settings</i>")]
    end

    subgraph outputs["Output Backends"]
        redis["Redis<br/><i>cache + pub/sub</i>"]
        influxdb["InfluxDB<br/><i>time-series storage</i>"]
        future_prom["Prometheus<br/><i>planned</i>"]
        future_pg["PostgreSQL<br/><i>planned</i>"]
    end

    subgraph api_layer["REST API (FastAPI)"]
        loc_routes["/api/v1/locations"]
        weather_routes["/api/v1/weather"]
        backend_routes["/api/v1/config/backends"]
        system_routes["/health, /docs"]
    end

    webui["Web UI<br/>(Jinja2 templates)"]

    %% Scheduler triggers collector
    scheduler -->|"triggers"| collector

    %% Collector reads locations from DB
    locations -.->|"read enabled<br/>locations"| collector

    %% API selection logic
    select -->|"US / preferred=noaa"| noaa
    select -->|"preferred=open-meteo<br/>or international"| openmeteo
    select -->|"preferred=openweather"| openweather

    %% Store results
    store -->|"write"| weather_data
    store -->|"upsert"| alerts_table

    %% Output distribution
    backend_config -.->|"read enabled<br/>backends"| distribute
    distribute -->|"write"| redis
    distribute -->|"write"| influxdb
    distribute -.->|"future"| future_prom
    distribute -.->|"future"| future_pg

    %% API layer reads from DB
    weather_data -.->|"read"| weather_routes
    alerts_table -.->|"read"| weather_routes
    locations -.->|"CRUD"| loc_routes
    backend_config -.->|"CRUD"| backend_routes

    %% Web UI talks to API
    webui <-->|"HTTP"| api_layer

    %% Styling
    style scheduler fill:#4a90d9,color:#fff
    style apis fill:#f5a623,color:#000
    style db fill:#7ed321,color:#000
    style outputs fill:#9b59b6,color:#fff
    style api_layer fill:#e74c3c,color:#fff
    style future_prom fill:#ccc,color:#666,stroke-dasharray: 5 5
    style future_pg fill:#ccc,color:#666,stroke-dasharray: 5 5
```

### Data Flow

1. **Scheduler** triggers the collector on a configurable interval (default 5 minutes)
2. **Collector** reads all enabled locations from the database
3. For each location, the collector **selects the appropriate weather API** based on country code and user preference:
   - US locations default to **NOAA**
   - International locations default to **Open-Meteo**
   - Per-location override via `preferred_api` field
4. API responses are **normalized** into a common `WeatherData` / `WeatherAlert` format
5. Data is **stored in the database** (SQLite or PostgreSQL)
6. Data is **distributed to output backends** (Redis, InfluxDB) based on enabled backend configs
7. The **REST API** serves cached data from the database; use `?fresh=true` to fetch live

### Output Backend Details

| Backend | Status | Measurement Format | Use Case |
|---------|--------|-------------------|----------|
| **Redis** | Active | Pluggable format transforms (e.g., kurokuu) | Cache, pub/sub, IoT displays |
| **InfluxDB** | Active | `weather` and `weather_alert` measurements with location/country/source tags | Time-series analysis, Grafana dashboards |
| Prometheus | Planned | Metrics endpoint | Monitoring and alerting |
| PostgreSQL | Planned | Relational tables | Direct SQL queries |

## Quick Start

### Using Docker (Recommended)

From the project root directory:

```bash
# Build and start the service
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop the service
docker-compose down
```

The API will be available at `http://localhost:8000`

### Local Development with uv

```bash
cd backend

# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head

# Start the development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, visit:
- Interactive API docs: `http://localhost:8000/docs`
- Alternative API docs: `http://localhost:8000/redoc`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration
```

## Code Quality

```bash
# Format and lint with ruff
uv run ruff check .
uv run ruff format .

# Type checking with mypy
uv run mypy app
```

## Database Migrations

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

## Configuration

Configuration is managed through environment variables or a `.env` file:

```env
# Application
APP_NAME=nalssi
APP_VERSION=0.1.0
DATABASE_URL=sqlite:///./nalssi.db
LOG_LEVEL=INFO
JSON_LOGS=false

# Scheduler
ENABLE_SCHEDULER=true
DEFAULT_COLLECTION_INTERVAL=300

# Weather APIs
NOAA_API_BASE_URL=https://api.weather.gov
OPEN_METEO_API_BASE_URL=https://api.open-meteo.com/v1
OPENWEATHER_API_KEY=your-key-here

# InfluxDB (optional)
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-token
INFLUXDB_ORG=your-org
INFLUXDB_BUCKET=weather

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# Server
API_HOST=0.0.0.0
API_PORT=8000
```

### SQLite Disk Persistence

The application configures SQLite for **immediate disk persistence** to avoid surprises when manually querying the database:

**PRAGMAs set automatically:**
- `synchronous=FULL` - Full fsync on every commit (data immediately written to disk)
- `journal_mode=DELETE` - Traditional rollback journal (simpler than WAL mode)
- `foreign_keys=ON` - Enforce foreign key constraints

**Trade-off:** This prioritizes **data safety over performance**. For production with high write volume, use PostgreSQL:
```env
DATABASE_URL=postgresql://user:password@localhost/nalssi
```

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── deps.py              # Dependency injection
│   │   └── routes/              # API endpoints
│   │       ├── locations.py     # Location CRUD
│   │       ├── weather.py       # Weather data & alerts
│   │       ├── backends.py      # Output backend config
│   │       ├── system.py        # Health check
│   │       └── pages/           # Web UI pages
│   ├── models/                  # SQLAlchemy models
│   │   ├── location.py
│   │   ├── weather.py
│   │   ├── alert.py
│   │   └── backend_config.py
│   ├── schemas/                 # Pydantic schemas
│   ├── services/
│   │   ├── collectors/
│   │   │   └── weather_collector.py
│   │   ├── weather_apis/        # Weather API clients
│   │   │   ├── base.py          # ABC + WeatherData/WeatherAlert
│   │   │   ├── noaa.py
│   │   │   ├── open_meteo.py
│   │   │   └── openweather.py
│   │   ├── outputs/             # Output backends
│   │   │   ├── base.py          # ABC + WriteResult
│   │   │   ├── manager.py       # Output distribution
│   │   │   ├── redis_backend.py
│   │   │   ├── influxdb_backend.py
│   │   │   └── formats/         # Pluggable format transforms
│   │   └── scheduler.py
│   ├── config.py                # Pydantic Settings
│   ├── database.py              # SQLAlchemy setup
│   └── main.py                  # FastAPI application
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test fixtures (API responses)
├── alembic/                     # Database migrations
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2025-12-24T..."
}
```

## Example API Usage

### Create a location

```bash
curl -X POST http://localhost:8000/api/v1/locations \
  -H "Content-Type: application/json" \
  -d '{
    "name": "San Francisco, CA",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "timezone": "America/Los_Angeles",
    "country_code": "US",
    "enabled": true,
    "collection_interval": 300,
    "preferred_api": "noaa"
  }'
```

### Get current weather

By default, returns cached data from the database:
```bash
curl http://localhost:8000/api/v1/locations/{location_id}/weather/current
```

To fetch fresh data from the weather API:
```bash
curl "http://localhost:8000/api/v1/locations/{location_id}/weather/current?fresh=true"
```

### Get weather alerts

By default, returns cached active alerts from the database:
```bash
curl http://localhost:8000/api/v1/locations/{location_id}/alerts
```

To fetch fresh alerts from the weather API:
```bash
curl "http://localhost:8000/api/v1/locations/{location_id}/alerts?fresh=true"
```

### Configure an InfluxDB output backend

```bash
curl -X POST http://localhost:8000/api/v1/config/backends \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My InfluxDB",
    "backend_type": "influxdb",
    "enabled": true,
    "connection_config": "{\"url\": \"http://localhost:8086\", \"token\": \"my-token\", \"org\": \"my-org\", \"bucket\": \"weather\"}"
  }'
```

### Configure a Redis output backend

```bash
curl -X POST http://localhost:8000/api/v1/config/backends \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Redis",
    "backend_type": "redis",
    "enabled": true,
    "format_type": "kurokku",
    "connection_config": "{\"url\": \"redis://localhost:6379/0\"}"
  }'
```

## Weather Collection

### Automatic Scheduled Collection

The service includes a **background scheduler** (APScheduler) that automatically collects weather data:

- Runs at the configured interval (default: 300 seconds / 5 minutes)
- Collects weather for all enabled locations
- Stores data in the database for fast retrieval
- Distributes to all enabled output backends
- Handles errors gracefully with logging

**Disable scheduler for testing:**
```bash
ENABLE_SCHEDULER=false uv run uvicorn app.main:app --reload
```

### Alert Collection and Storage

Weather alerts are automatically collected alongside weather data:

- Each alert has an external `alert_id` from the source API
- Unique constraint on (location_id, alert_id, source_api) prevents duplicates
- Existing alerts are updated in place (upsert behavior)
- The `/alerts` endpoint returns only active (non-expired) alerts by default

## Supported Weather APIs

| API | Coverage | Cost | API Key |
|-----|----------|------|---------|
| **NOAA Weather.gov** | US only | Free | Not required |
| **Open-Meteo** | Global | Free (non-commercial) | Not required |
| **OpenWeatherMap** | Global | Free tier available | Required |

## Development Workflow

This project follows Test-Driven Development (TDD):

1. Write tests first (red phase)
2. Implement minimal code to pass tests (green phase)
3. Refactor while keeping tests green (refactor phase)

## License

[Add license information]
