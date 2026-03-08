# Nalssi - Weather Data Collection Service

## Project Overview

Nalssi is a centralized weather data collection and distribution service designed to:
- Collect weather data from multiple locations using free/low-cost APIs
- Store data in multiple configurable backends (InfluxDB, Prometheus, Redis, PostgreSQL/SQLite)
- Provide a web interface for configuration and data viewing
- Expose a REST API for programmatic access
- Run as a containerized Docker service

**Purpose**: Centralize weather API calls so multiple applications can consume weather data without each making their own API requests, reducing costs and API rate limit concerns.

**Project Decisions**:
- **Use Case**: Non-commercial use
- **Geographic Focus**: Primary focus on US locations, with extensible support for international locations
- **Frontend**: React for web interface
- **Dependency Management**: `uv` for Python dependencies
- **API Framework**: FastAPI
- **Code Quality**: `ruff` for linting and formatting
- **Testing**: `pytest` with Test-Driven Development (TDD) approach

## Weather API Recommendations

Based on research, here are the recommended weather APIs for keeping costs low:

### Primary Recommendation: Multi-API Strategy

1. **NOAA Weather.gov API** (api.weather.gov)
   - **Cost**: Completely FREE, no API key required
   - **Coverage**: US locations only
   - **Features**: Current conditions, forecasts, alerts/warnings/watches (CAP format)
   - **Limits**: Reasonable rate limits to prevent abuse
   - **Best for**: US-based alerts and warnings (core requirement)
   - **Docs**: https://www.weather.gov/documentation/services-web-api

2. **Open-Meteo** (open-meteo.com)
   - **Cost**: FREE for non-commercial use
   - **Coverage**: Global
   - **Features**: Current weather, forecasts, historical data
   - **Limits**: ~10,000 calls/day recommended for non-commercial
   - **API Key**: Not required
   - **Response time**: <10ms
   - **Best for**: International locations or backup for NOAA
   - **Docs**: https://open-meteo.com/

3. **WeatherAPI.com** (weatherapi.com) - Backup/High Volume
   - **Cost**: FREE tier with 1M calls/month
   - **Coverage**: Global
   - **Features**: Current, forecast, alerts, astronomy
   - **API Key**: Required (free)
   - **Best for**: High-volume needs or commercial use
   - **Docs**: https://www.weatherapi.com/docs/

### API Strategy (Extensible Design)
**Primary Strategy**:
- **US Locations**: NOAA Weather.gov API (free, no key, comprehensive alerts)
- **International Locations**: Open-Meteo (free for non-commercial, global coverage)
- **Optional**: WeatherAPI.com for higher volume or additional features

**Extensibility**:
- Abstract base class for weather API providers enables easy addition of new APIs
- Location-based routing: auto-select API based on country code (US → NOAA, others → Open-Meteo)
- Manual override: allow per-location API preference
- Fallback chain: if primary API fails, try backup (e.g., NOAA fails → try Open-Meteo)
- Plugin architecture: new weather APIs can be added by implementing the base interface

**API Selection Logic**:
```python
def select_api_for_location(location):
    if location.country_code == "US" and location.preferred_api is None:
        return "noaa"  # Default for US
    elif location.preferred_api:
        return location.preferred_api  # User override
    else:
        return "open-meteo"  # Default for international
```

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Nalssi Service                       │
│                                                              │
│  ┌────────────────┐      ┌──────────────────┐              │
│  │  Web Frontend  │◄────►│   REST API       │              │
│  │  (React/Vue)   │      │   (FastAPI)      │              │
│  └────────────────┘      └──────────────────┘              │
│                                   │                          │
│                          ┌────────▼────────┐                │
│                          │  Core Service   │                │
│                          │  - Scheduler    │                │
│                          │  - Collectors   │                │
│                          │  - Processors   │                │
│                          └────────┬────────┘                │
│                                   │                          │
│           ┌───────────────────────┼───────────────────────┐ │
│           │                       │                       │ │
│  ┌────────▼────────┐   ┌─────────▼────────┐   ┌─────────▼─┤
│  │ Config Storage  │   │  Weather APIs    │   │  Output   │ │
│  │ (SQLite/PG)     │   │  - NOAA          │   │  Backends │ │
│  │                 │   │  - Open-Meteo    │   │           │ │
│  │ - Locations     │   │  - WeatherAPI    │   │ - InfluxDB│ │
│  │ - API Keys      │   └──────────────────┘   │ - Prometh.│ │
│  │ - Backend Config│                          │ - Redis   │ │
│  │ - Settings      │                          │ - PG/SQLit│ │
│  └─────────────────┘                          └───────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. Core Service Layer
- **Weather Collector**: Fetches data from configured weather APIs
- **Scheduler**: Manages collection intervals (configurable per location)
- **Data Processor**: Normalizes data from different APIs into common format
- **Output Manager**: Distributes data to configured backends
- **Configuration Manager**: Handles settings, locations, API keys

#### 2. Storage Layer
- **Configuration Database** (SQLite default, PostgreSQL optional)
  - Locations to monitor
  - API keys and credentials
  - Backend configurations
  - Collection schedules
  - User settings

#### 3. Output Backends (all optional, configurable)
- **InfluxDB**: Time-series storage (ideal for weather data)
- **Prometheus**: Metrics endpoint (for monitoring/alerting)
- **Redis**: Fast cache/pub-sub for real-time consumers
- **PostgreSQL/SQLite**: Relational storage for applications

#### 4. API Layer (FastAPI)
- RESTful API for all operations
- Authentication/authorization (API keys or JWT)
- OpenAPI documentation (auto-generated)

#### 5. Web Interface
- Configuration dashboard
- Location management
- Real-time weather viewing
- Backend status monitoring
- API key management

## Technology Stack

### Backend
- **Python 3.11+**: Core language
- **FastAPI**: REST API framework
  - Fast, modern, automatic OpenAPI docs
  - Async support for concurrent API calls
  - Easy dependency injection
- **SQLAlchemy**: ORM for database
- **Alembic**: Database migrations
- **APScheduler**: Job scheduling for weather collection
- **Pydantic**: Data validation and settings management
- **httpx**: Async HTTP client for weather APIs
- **Redis-py**: Redis client (optional)
- **InfluxDB-client**: InfluxDB integration (optional)
- **Psycopg2/asyncpg**: PostgreSQL support (optional)

### Frontend
- **React**: Modern web framework with hooks
- **Vite**: Fast build tool and dev server
- **Tailwind CSS**: Utility-first styling framework
- **Recharts**: React-based weather data visualization
- **Axios**: API communication
- **React Router**: Client-side routing
- **React Query** or **SWR**: Server state management

### Development Tools & Testing
- **pytest**: Testing framework
  - Async support with pytest-asyncio
  - Fixtures for database and API testing
  - Coverage reporting with pytest-cov
- **ruff**: All-in-one linter and formatter
  - Extremely fast (written in Rust)
  - Replaces black, flake8, isort, pyupgrade, and more
  - Auto-fix capabilities
  - 100% compatible with Black formatting
- **mypy**: Static type checking (optional but recommended)
- **httpx**: For testing API clients (same library used for production)

### DevOps
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration
- **Uvicorn**: ASGI server for FastAPI
- **Nginx**: Reverse proxy (optional, in production)
- **uv**: Fast Python package and project manager
  - Modern, extremely fast alternative to pip/pip-tools/poetry
  - Built in Rust, 10-100x faster than pip
  - Compatible with pip/requirements.txt
  - Built-in virtual environment management

## Data Models

### Location
```python
{
  "id": "uuid",
  "name": "San Francisco, CA",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "timezone": "America/Los_Angeles",
  "country_code": "US",
  "enabled": true,
  "collection_interval": 300,  # seconds
  "preferred_api": "noaa",  # or "open-meteo", "weatherapi", "auto"
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Weather Data (Normalized)
```python
{
  "id": "uuid",
  "location_id": "uuid",
  "timestamp": "timestamp",
  "source_api": "noaa",

  # Current conditions
  "temperature": 18.5,  # Celsius
  "temperature_fahrenheit": 65.3,
  "feels_like": 17.2,
  "humidity": 65,  # percentage
  "pressure": 1013.25,  # hPa
  "wind_speed": 5.5,  # m/s
  "wind_direction": 270,  # degrees
  "wind_gust": 8.2,
  "precipitation": 0.0,  # mm
  "cloud_cover": 40,  # percentage
  "visibility": 10000,  # meters
  "uv_index": 3,

  # Conditions
  "condition_code": "partly_cloudy",
  "condition_text": "Partly Cloudy",
  "icon": "02d",

  # Additional
  "sunrise": "timestamp",
  "sunset": "timestamp",
  "alerts": [...],  # JSON array of active alerts

  "raw_data": {...},  # Original API response
  "created_at": "timestamp"
}
```

### Alert/Warning
```python
{
  "id": "uuid",
  "location_id": "uuid",
  "alert_id": "external_id",  # From NOAA/API
  "event": "Severe Thunderstorm Warning",
  "severity": "severe",  # extreme, severe, moderate, minor
  "urgency": "immediate",  # immediate, expected, future
  "headline": "Severe Thunderstorm Warning issued...",
  "description": "Full alert text...",
  "instruction": "Take shelter...",
  "effective": "timestamp",
  "expires": "timestamp",
  "areas": ["San Francisco County"],
  "source": "noaa",
  "created_at": "timestamp"
}
```

### Forecast
```python
{
  "id": "uuid",
  "location_id": "uuid",
  "forecast_date": "date",
  "period": "day",  # or "night", "hour_1", "hour_3", etc.

  "temp_high": 22.0,
  "temp_low": 12.0,
  "condition_code": "rain",
  "condition_text": "Light Rain",
  "precipitation_probability": 60,  # percentage
  "precipitation_amount": 2.5,  # mm
  "wind_speed": 4.2,
  "humidity": 70,

  "source_api": "noaa",
  "fetched_at": "timestamp",
  "created_at": "timestamp"
}
```

### API Configuration
```python
{
  "id": "uuid",
  "provider": "noaa",  # or "open-meteo", "weatherapi"
  "enabled": true,
  "api_key": "encrypted_key",  # null for NOAA/Open-Meteo
  "rate_limit": 60,  # requests per minute
  "priority": 1,  # Lower = higher priority
  "config": {...},  # Provider-specific settings
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Output Backend Configuration
```python
{
  "id": "uuid",
  "backend_type": "influxdb",  # or "prometheus", "redis", "postgresql"
  "enabled": true,
  "name": "Production InfluxDB",
  "connection_config": {
    "host": "influxdb.example.com",
    "port": 8086,
    "database": "weather",
    "username": "encrypted",
    "password": "encrypted",
    "ssl": true
  },
  "data_retention": 30,  # days, null for infinite
  "write_interval": 60,  # seconds, batch writes
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

## REST API Design

### Base URL: `/api/v1`

#### Locations
- `GET /locations` - List all locations
- `POST /locations` - Add new location
- `GET /locations/{id}` - Get location details
- `PUT /locations/{id}` - Update location
- `DELETE /locations/{id}` - Remove location
- `GET /locations/{id}/weather/current` - Current weather for location
- `GET /locations/{id}/weather/forecast` - Forecast for location
- `GET /locations/{id}/alerts` - Active alerts for location

#### Weather Data
- `GET /weather/current` - Current weather for all locations
- `GET /weather/forecast` - Forecasts for all locations
- `GET /weather/alerts` - All active alerts
- `GET /weather/history` - Historical data (query params: location, start, end)

#### Configuration
- `GET /config/apis` - List configured weather APIs
- `POST /config/apis` - Add API configuration
- `PUT /config/apis/{id}` - Update API configuration
- `DELETE /config/apis/{id}` - Remove API configuration

- `GET /config/backends` - List output backends
- `POST /config/backends` - Add backend
- `PUT /config/backends/{id}` - Update backend
- `DELETE /config/backends/{id}` - Remove backend
- `POST /config/backends/{id}/test` - Test backend connection

#### System
- `GET /health` - Service health check
- `GET /metrics` - Prometheus metrics endpoint
- `GET /status` - Collection status, last run times, errors
- `POST /collect/trigger` - Manually trigger collection
- `GET /logs` - Recent logs (filtered by level, component)

#### Authentication
- `POST /auth/login` - Get JWT token
- `POST /auth/refresh` - Refresh token
- `GET /auth/apikeys` - List API keys
- `POST /auth/apikeys` - Create new API key
- `DELETE /auth/apikeys/{id}` - Revoke API key

## Output Backend Implementations

### InfluxDB
```python
# Write current weather as measurements
weather,location=SF,source=noaa temperature=18.5,humidity=65,pressure=1013.25 1234567890

# Tags: location, source, condition
# Fields: All numeric weather values
# Timestamp: Observation time
```

### Prometheus
```python
# Expose metrics endpoint at /metrics
weather_temperature{location="SF",source="noaa"} 18.5
weather_humidity{location="SF",source="noaa"} 65
weather_pressure{location="SF",source="noaa"} 1013.25
weather_alert_active{location="SF",severity="severe"} 1
```

### Redis
```python
# Current weather cache
SET weather:current:SF:latest {json_data} EX 300

# Pub/Sub for real-time updates
PUBLISH weather:updates {json_data}

# Alerts
SET weather:alerts:SF:active {json_array} EX 3600
```

### PostgreSQL/SQLite
```sql
-- Use normalized schema (same as internal storage)
-- Applications can query directly
-- Support for complex queries, joins, aggregations
```

## Project Structure

```
nalssi/
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.web
│   └── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI application
│   │   ├── config.py            # Settings/configuration
│   │   ├── database.py          # Database setup
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── location.py
│   │   │   ├── weather.py
│   │   │   ├── alert.py
│   │   │   ├── api_config.py
│   │   │   └── backend_config.py
│   │   ├── schemas/             # Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── location.py
│   │   │   ├── weather.py
│   │   │   └── config.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py          # Dependencies
│   │   │   ├── routes/
│   │   │   │   ├── locations.py
│   │   │   │   ├── weather.py
│   │   │   │   ├── config.py
│   │   │   │   ├── auth.py
│   │   │   │   └── system.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── scheduler.py     # APScheduler setup
│   │   │   ├── collector.py     # Main collection orchestrator
│   │   │   ├── weather_apis/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py      # Abstract base class
│   │   │   │   ├── noaa.py
│   │   │   │   ├── open_meteo.py
│   │   │   │   └── weatherapi.py
│   │   │   ├── processors/
│   │   │   │   ├── __init__.py
│   │   │   │   └── normalizer.py  # Normalize API responses
│   │   │   └── outputs/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── influxdb.py
│   │   │       ├── prometheus.py
│   │   │       ├── redis.py
│   │   │       └── postgresql.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── security.py      # Auth, encryption
│   │   │   └── utils.py
│   │   └── migrations/          # Alembic migrations
│   │       └── versions/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_api.py
│   │   ├── test_collectors.py
│   │   └── test_outputs.py
│   ├── pyproject.toml           # uv project configuration
│   ├── uv.lock                  # uv lock file
│   └── README.md
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── LocationManager.jsx
│   │   │   ├── WeatherCard.jsx
│   │   │   ├── AlertsPanel.jsx
│   │   │   ├── BackendConfig.jsx
│   │   │   └── Settings.jsx
│   │   ├── services/
│   │   │   └── api.js           # API client
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── init_db.py
│   └── seed_sample_data.py
├── .env.example
├── .gitignore
├── README.md
├── CLAUDE.md                    # This file
└── LICENSE
```

## Quick Start for Development

### Prerequisites
- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) installed: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker and Docker Compose (for containerized deployment)
- Node.js 18+ and npm (for frontend development)

### Initial Setup

```bash
# Clone/create project directory
cd /Users/steven/projects/nalssi

# Initialize Python project with uv
uv init backend
cd backend

# Add dependencies
uv add fastapi uvicorn[standard] sqlalchemy alembic pydantic-settings httpx apscheduler

# Add dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov ruff mypy

# Create virtual environment and install
uv sync

# Run linter and formatter
uv run ruff check .              # Lint code
uv run ruff check --fix .        # Auto-fix issues
uv run ruff format .             # Format code
uv run mypy app                  # Type check

# Run tests
uv run pytest                    # Run all tests
uv run pytest -v                 # Verbose output
uv run pytest --cov=app          # With coverage report
uv run pytest -k test_name       # Run specific test

# Run development server (once code is written)
uv run uvicorn app.main:app --reload
```

### Frontend Setup (Phase 5)

```bash
cd frontend

# Initialize React + Vite project
npm create vite@latest . -- --template react

# Install dependencies
npm install axios react-router-dom recharts

# Install Tailwind CSS
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Run development server
npm run dev
```

### Docker Quick Start

```bash
# Build and run all services
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Development Phases

### Phase 1: Core Foundation (MVP)
**Goal**: Basic working service with single API and single output

**TDD Approach**: Write tests first for each component

- [ ] Project setup (directory structure, dependencies with uv)
- [ ] Configure ruff, pytest, mypy in pyproject.toml
- [ ] Set up test structure (conftest.py, fixtures)
- [ ] **TDD**: Database models and migrations (SQLAlchemy + Alembic)
  - Write tests for Location, WeatherData models
  - Implement models to pass tests
  - Create Alembic migrations
- [ ] **TDD**: Configuration management (Pydantic settings)
  - Write tests for settings validation
  - Implement settings classes
- [ ] **TDD**: NOAA Weather.gov API client implementation
  - Write tests with mocked API responses
  - Implement client to pass tests
  - Add error handling, retries
- [ ] **TDD**: Basic scheduler (APScheduler) for periodic collection
  - Write tests with mocked time
  - Implement scheduler
- [ ] SQLite storage (internal + output backend)
- [ ] **TDD**: Basic FastAPI endpoints for locations and weather data
  - Write API endpoint tests
  - Implement endpoints
  - Test error cases
- [ ] Docker containerization
- [ ] Basic health check and logging
- [ ] Achieve 80%+ test coverage

**Deliverable**: Docker service that collects weather from NOAA for configured locations and stores in SQLite, with comprehensive test suite

### Phase 2: Multi-API Support
**Goal**: Support multiple weather API providers

- [ ] Abstract weather API base class
- [ ] Open-Meteo API client
- [ ] WeatherAPI.com client
- [ ] API provider selection logic (by location, fallback)
- [ ] Data normalization layer
- [ ] API configuration management (CRUD endpoints)
- [ ] Rate limiting and error handling
- [ ] API health monitoring

**Deliverable**: Service can use multiple weather APIs with automatic fallback

### Phase 3: Output Backends
**Goal**: Support multiple output destinations

- [ ] Abstract output backend base class
- [ ] InfluxDB output implementation
- [ ] Redis output implementation
- [ ] Prometheus metrics endpoint
- [ ] PostgreSQL output implementation
- [ ] Backend configuration CRUD endpoints
- [ ] Connection testing and validation
- [ ] Error handling and retry logic
- [ ] Batch writing for efficiency

**Deliverable**: Weather data distributed to multiple configured backends

### Phase 4: Alerts & Forecasts
**Goal**: Full weather data including alerts and forecasts

- [ ] Alert/warning data models
- [ ] NOAA alerts API integration (CAP format)
- [ ] Alert storage and retrieval
- [ ] Forecast data models
- [ ] Forecast collection and storage
- [ ] Alert notification system (optional: webhook, email)
- [ ] Historical data cleanup/retention policies

**Deliverable**: Complete weather data including current, forecast, and alerts

### Phase 5: Web Interface
**Goal**: User-friendly configuration and monitoring

- [ ] Frontend project setup (React/Vue)
- [ ] Authentication UI (login, API key management)
- [ ] Dashboard with current weather overview
- [ ] Location management interface
- [ ] Weather data visualization (charts, maps)
- [ ] Alerts display panel
- [ ] Backend configuration interface
- [ ] API configuration interface
- [ ] System status and monitoring page
- [ ] Real-time updates (WebSocket or polling)

**Deliverable**: Full-featured web interface

### Phase 6: Production Readiness
**Goal**: Production-grade deployment and operations

- [ ] Authentication & authorization (JWT, API keys)
- [ ] Input validation and sanitization
- [ ] Comprehensive error handling
- [ ] Structured logging (JSON format)
- [ ] Metrics and monitoring (Prometheus)
- [ ] Health checks (liveness, readiness)
- [ ] Docker Compose with all services
- [ ] Environment-based configuration
- [ ] Secrets management
- [ ] Documentation (API docs, deployment guide)
- [ ] Unit and integration tests
- [ ] Performance optimization
- [ ] Database backups

**Deliverable**: Production-ready service with monitoring and documentation

## Configuration Management

### Environment Variables (.env file)
```bash
# Application
APP_NAME=nalssi
APP_VERSION=1.0.0
LOG_LEVEL=INFO
DEBUG=false

# Database
DATABASE_URL=sqlite:///./nalssi.db
# DATABASE_URL=postgresql://user:pass@localhost/nalssi

# Security
SECRET_KEY=your-secret-key-here
API_KEY_ENCRYPTION_KEY=your-encryption-key

# Weather APIs
NOAA_API_BASE_URL=https://api.weather.gov
OPEN_METEO_API_BASE_URL=https://api.open-meteo.com/v1
WEATHERAPI_API_KEY=your-key-if-using

# Collection
DEFAULT_COLLECTION_INTERVAL=300  # seconds
MAX_CONCURRENT_COLLECTIONS=5

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# InfluxDB (optional)
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=your-token
INFLUXDB_ORG=your-org
INFLUXDB_BUCKET=weather

# Server
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_HOST=0.0.0.0
FRONTEND_PORT=3000
```

### Development Tool Configuration

#### pyproject.toml (ruff, pytest, mypy config)
```toml
[project]
name = "nalssi"
version = "0.1.0"
description = "Weather data collection and distribution service"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.12.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.25.0",
    "apscheduler>=3.10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]

[tool.ruff]
# Enable pycodestyle (`E`), Pyflakes (`F`), isort (`I`), and more
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # Pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "SIM",  # flake8-simplify
]
ignore = [
    "E501",  # line too long (handled by formatter)
]

# Exclude common directories
exclude = [
    ".git",
    ".venv",
    "__pycache__",
    "migrations",
    "build",
    "dist",
]

# Same as Black
line-length = 88
indent-width = 4

# Target Python 3.11+
target-version = "py311"

[tool.ruff.format]
# Use double quotes for strings
quote-style = "double"

# Indent with spaces
indent-style = "space"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"

# Coverage options
addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-report=xml",
]

# Markers for organizing tests
markers = [
    "unit: Unit tests (fast, isolated)",
    "integration: Integration tests (slower, uses database)",
    "e2e: End-to-end tests (slowest, full workflow)",
    "slow: Tests that take significant time",
]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Start lenient, tighten later
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

#### .ruff.toml (alternative standalone config)
If you prefer a standalone config file instead of pyproject.toml:

```toml
# Ruff configuration
line-length = 88
target-version = "py311"

[lint]
select = ["E", "W", "F", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[format]
quote-style = "double"
indent-style = "space"
```

## Deployment Strategy

### Development
```bash
docker-compose up --build
```

### Production
```bash
# Using Docker Compose with production config
docker-compose -f docker-compose.prod.yml up -d

# Or Kubernetes manifests for cloud deployment
# Or systemd service for bare metal
```

### Scaling Considerations
- Scheduler runs on single instance (leader election for HA)
- API can scale horizontally (stateless)
- Use external PostgreSQL/Redis for multi-instance deployments
- Consider message queue (RabbitMQ/Redis) for distributed collection

## Security Considerations

1. **API Key Management**
   - Encrypt API keys at rest
   - Use environment variables or secrets manager
   - Never log sensitive data

2. **Authentication**
   - JWT tokens for web interface
   - API keys for programmatic access
   - Rate limiting per user/key

3. **Input Validation**
   - Pydantic models for all inputs
   - Validate lat/lon ranges
   - Sanitize user-provided names

4. **Network Security**
   - HTTPS/TLS for all external communication
   - Secure backend connections (Redis AUTH, InfluxDB tokens)
   - Network isolation in Docker

5. **Data Privacy**
   - No PII collection required
   - Audit logging for configuration changes
   - Configurable data retention

## Testing Strategy

### Test-Driven Development (TDD) Approach

We'll follow TDD principles throughout development:

**TDD Cycle (Red-Green-Refactor)**:
1. 🔴 **Red**: Write a failing test first
2. 🟢 **Green**: Write minimal code to make test pass
3. 🔵 **Refactor**: Clean up code while keeping tests green

**Benefits**:
- Forces clear API design before implementation
- Ensures comprehensive test coverage
- Creates living documentation
- Catches regressions early
- Enables confident refactoring

**TDD Example Workflow**:
```python
# Step 1: Write failing test
def test_noaa_client_fetches_current_weather():
    client = NOAAWeatherClient()
    data = client.get_current_weather(lat=37.7749, lon=-122.4194)
    assert data.temperature is not None
    assert data.condition is not None

# Step 2: Implement minimal code to pass
class NOAAWeatherClient:
    def get_current_weather(self, lat, lon):
        # Minimal implementation
        pass

# Step 3: Refactor and enhance
# Add error handling, logging, proper API calls, etc.
```

### Testing Framework & Tools

- **pytest**: Primary testing framework
- **pytest-asyncio**: For async/await test functions
- **pytest-cov**: Coverage reporting (aim for 80%+ coverage)
- **pytest fixtures**: Database setup, API mocking, test data
- **httpx MockTransport**: Mock HTTP requests to weather APIs
- **freezegun**: Mock datetime for time-based tests

### Test Categories

1. **Unit Tests** (Fast, Isolated)
   - Individual weather API clients
   - Data processors/normalizers
   - Output backend implementations
   - Utility functions
   - Pydantic models and validation
   - **Run these frequently during development**

2. **Integration Tests** (Slower, More Complete)
   - End-to-end collection flow
   - API endpoints with test database
   - Output backend writes
   - Database migrations
   - **Run before commits**

3. **Mocking Strategy**
   - Mock weather API HTTP responses (save real responses as fixtures)
   - Mock time/datetime for scheduler testing
   - Use in-memory SQLite for database tests
   - Mock external services (Redis, InfluxDB) in unit tests

### Test Structure

```
backend/tests/
├── conftest.py                 # Shared fixtures
├── fixtures/
│   ├── noaa_responses.json     # Real API responses
│   └── open_meteo_responses.json
├── unit/
│   ├── test_weather_apis/
│   │   ├── test_noaa_client.py
│   │   ├── test_open_meteo_client.py
│   │   └── test_base_client.py
│   ├── test_processors/
│   │   └── test_normalizer.py
│   ├── test_outputs/
│   │   ├── test_influxdb_output.py
│   │   └── test_redis_output.py
│   └── test_models.py
├── integration/
│   ├── test_api_endpoints.py
│   ├── test_collection_flow.py
│   └── test_scheduler.py
└── e2e/
    └── test_full_workflow.py
```

### Coverage Goals

- **Minimum**: 80% code coverage
- **Target**: 90%+ for core business logic
- **Focus areas**: Weather API clients, data processors, output backends
- **Less critical**: Utility functions, configuration code

### Continuous Testing

```bash
# Watch mode during development
uv run pytest-watch

# Pre-commit hook (run automatically)
uv run pytest --cov=app --cov-report=term-missing

# CI/CD pipeline
uv run pytest --cov=app --cov-report=xml --cov-fail-under=80
```

## Documentation Requirements

1. **README.md**
   - Project overview
   - Quick start guide
   - Docker deployment
   - Configuration examples

2. **API Documentation**
   - Auto-generated OpenAPI/Swagger
   - Example requests/responses
   - Authentication guide

3. **Developer Guide**
   - Architecture overview
   - Adding new weather APIs
   - Adding new output backends
   - Testing guide

4. **Deployment Guide**
   - Docker Compose setup
   - Environment configuration
   - Backup and recovery
   - Monitoring setup

## Future Enhancements (Post-MVP)

1. **Advanced Features**
   - Webhook notifications for alerts
   - Email/SMS alerts
   - Weather-based automation triggers
   - Historical data analysis and trends
   - GraphQL API option

2. **Additional Weather APIs**
   - Tomorrow.io
   - Weather Underground
   - Weatherbit
   - AccuWeather

3. **Additional Outputs**
   - Kafka/Pulsar for streaming
   - Elasticsearch for search
   - TimescaleDB optimization
   - MQTT for IoT devices

4. **Data Enrichment**
   - Air quality data
   - Pollen levels
   - Astronomy data (moon phase, etc.)
   - Severe weather imagery

5. **UI Enhancements**
   - Mobile app (React Native)
   - Weather maps and radar
   - Customizable dashboards
   - Export to CSV/JSON
   - Multi-language support

## Resources

### Weather API Documentation
- [NOAA Weather.gov API](https://www.weather.gov/documentation/services-web-api)
- [NOAA Alerts Web Service](https://www.weather.gov/documentation/services-web-alerts)
- [Open-Meteo API](https://open-meteo.com/)
- [WeatherAPI.com Docs](https://www.weatherapi.com/docs/)

### Technology Documentation
- [uv - Python package manager](https://docs.astral.sh/uv/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://docs.sqlalchemy.org/)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [InfluxDB Python Client](https://influxdb-client.readthedocs.io/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
- [React](https://react.dev/)
- [Vite](https://vitejs.dev/)
- [Tailwind CSS](https://tailwindcss.com/)

## License

TBD - Recommend MIT or Apache 2.0 for open source

---

## Next Steps

1. ✅ **Decisions Made**:
   - Non-commercial use (allows free Open-Meteo)
   - US primary, international support via extensible API design
   - React for frontend
   - `uv` for Python dependency management
   - FastAPI for REST API

2. **Ready to Begin Phase 1 Implementation**:
   - Initialize project with `uv`
   - Set up directory structure
   - Configure Docker development environment
   - Implement NOAA API client
   - Create basic data models and database
   - Build initial FastAPI endpoints

## Remaining Configuration Questions

These can be configured with sensible defaults and changed later:

1. **Collection Frequency**: Default to 5 minutes (300 seconds) for current weather, 1 hour for forecasts?
2. **Data Retention**: Keep 30 days of historical data by default? (configurable per backend)
3. **High Availability**: Start with single instance, design for HA but don't implement initially?
4. **Authentication**:
   - Phase 1: No auth (trusted network/localhost only)
   - Phase 2+: API keys for programmatic access
   - Phase 5+: JWT for web interface with user management
5. **Initial Output Backends**: Start with SQLite only in Phase 1, add others in Phase 3?
