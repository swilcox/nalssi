# Nalssi

[![CI](https://github.com/swilcox/nalssi/actions/workflows/ci.yml/badge.svg)](https://github.com/swilcox/nalssi/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/swilcox/nalssi/branch/main/graph/badge.svg)](https://codecov.io/gh/swilcox/nalssi)
[![Docker](https://github.com/swilcox/nalssi/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/swilcox/nalssi/actions/workflows/docker-publish.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Nalssi (날씨, Korean for "weather") is a centralized weather data collection and distribution service. It fetches weather data from multiple free APIs on a schedule, stores it locally, and distributes it to configurable output backends — so your other applications can consume weather data without each making their own API calls.

![Nalssi dashboard screenshot](docs/assets/screenshot.png)

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
- **Radar imagery** — Two hours of animated NWS reflectivity per location, collected server-side and served locally
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

## Radar Imagery

`/radar` lists every location with a still of its most recent frame; selecting
one opens `/radar/<location>`, the detail view with roughly two hours of
animated NWS reflectivity centered on that location.

The split keeps the list to one image per location rather than a full loop
each, so it stays fast as locations and retention grow.

Frames come from the NCEP GeoServer WMS (`opengeo.ncep.noaa.gov`), which needs no
API key and publishes a rolling ~2 hour time dimension at about 2 minute cadence.
Because any timestamp in that window can be requested directly, a newly added
location backfills its entire history on the first collection rather than warming
up over two hours.

Each location's basemap is fetched once and cached, since the view is a pure
function of its coordinates; only the transparent radar layer is stored per
frame. The basemap comes in three separately-stored bands — shaded water from
USGS hydrography, US counties, and state/province boundaries — which the viewer
colours independently so water, counties, and state lines are each
distinguishable. They are split rather than combined because the upstream
servers publish only line styles and refuse custom SLD, so the visual hierarchy
has to be applied client-side. A location holds roughly 1–2 MB at the default settings, pruned on a
rolling window. Storage for deleted locations, and basemaps superseded by a
settings change, are cleaned up on the next cycle.

Radar is fully feature-gated. With `RADAR_ENABLED=false` no radar routes are
registered at all and the nav item disappears, so a deployment focused on
alerts and observations carries none of it.

Locations that share coordinates share their imagery. Running the same place
under two providers (one NOAA, one OpenWeatherMap) is a normal setup, and those
locations resolve to the same radar view, so the frames are downloaded and
stored once and referenced by both.

Radar collection is independent of which weather API a location uses. The
source is chosen from the location's coordinates and country: US locations use
the NWS MRMS mosaic, Canadian locations use ECCC's MSC GeoMet (3 hours of
history at 6-minute steps). Coverage overlaps across the border — the US mosaic
reaches well into southern Canada — so a location's own national service wins
where both apply. Locations outside all covered areas are skipped
automatically.

See [docs/international-weather-services.md](docs/international-weather-services.md)
for what's available in Europe, Japan, and Korea, and what adding another
source involves.

The location itself is marked at the center of every frame, with configurable
distance rings around it. Both are SVG drawn over the images rather than baked
in, so they cost nothing to store and can be changed without refetching: the
location is the exact center pixel by construction, since the bounding box is
computed around its coordinates rather than taken from a prebuilt image.

Rings are drawn as plain circles. Web Mercator is conformal so they stay
circular, and the km-per-pixel scale drifts less than 2% across a 240 km view at
CONUS latitudes (about 3.5% in Alaska).

### Precipitation state for output backends

Alongside the imagery, each collection cycle asks the radar whether it is
currently precipitating over each location and passes that to the output
backends:

- **Redis (kurokku)** — `kurokku:weather:{slug}:precip` set to `Rain` or `Dry`
- **InfluxDB** — a `radar_precipitation` field (`1`/`0`) on the `weather`
  measurement, so a mean over a window reads as the fraction of time it was wet

The value is deliberately a boolean, not a reflectivity number. NOAA's public
radar services render a mosaic rather than exposing a data raster, so numeric
dBZ is not retrievable; only the rendered pixel's alpha channel is, which needs
no assumptions about NOAA's styling.

When the state is unknown — radar disabled, location outside coverage, or the
lookup failed — backends leave any existing value alone rather than reporting
`Dry`, the same way an alert fetch failure preserves existing alert state.

## Forecast

`/forecast` lists every location with a near-term outlook — the current period
plus the next few, with day and night marked separately. Selecting one opens
`/forecast/<location>` with every upcoming period in full detail.

As with radar, the split keeps the list compact rather than stacking a full
14-period grid per location down a single page.

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

## Kurokku Alert Priorities

When writing alerts to a Redis backend using the `kurokku` format, each alert is assigned a numeric priority (0 = highest, 5 = lowest) that the kurokku LED clock uses to decide display order.

Priority is determined in this order:

1. **Event keyword match** — the alert's `event` text is matched case-insensitively against the table below. When multiple keywords match (e.g. `severe thunderstorm` and `severe thunderstorm watch`), the longest keyword wins so more specific entries beat more general ones regardless of config order.
2. **CAP severity fallback** — if no keyword matches, the alert's CAP `severity` field (from NOAA) maps to a priority.
3. **Urgency bump** — if the CAP fallback was used and `urgency` is `Immediate`, priority is bumped up by one level (minimum 0).
4. **Default** — priority 5 if nothing else matches.

**Event keyword mapping (defaults):**

| Priority | Events |
|---------:|--------|
| 0 | tornado, tsunami, extreme wind, hurricane, typhoon, storm surge |
| 1 | flash flood, severe thunderstorm, blizzard |
| 2 | flood, winter storm, high wind, ice storm, excessive heat, fire weather |
| 3 | wind chill, freeze, frost, cold weather advisory, heat advisory, wind advisory, dense fog |
| 4 | winter weather, special weather |

**Watches:** All Watch events (e.g. `severe thunderstorm watch`, `hurricane watch`, `flood watch`) are mapped to priority **3**, with one exception: `tornado watch` is priority **2** due to its short lead time and life-safety risk. Because the matcher prefers the longest matching keyword, Watch events resolve to these Watch-specific entries rather than inheriting their Warning's priority.

**CAP severity fallback (when no keyword matches):**

| CAP Severity | Priority |
|--------------|---------:|
| Extreme | 1 |
| Severe  | 2 |
| Moderate | 3 |
| Minor   | 4 |
| Unknown | 5 |

### Overriding priorities per backend

The default mapping can be overridden on a per-backend basis by setting `alert_priorities` in the backend's Format Config JSON:

```json
{
  "alert_priorities": {
    "tornado": 0,
    "my custom event": 1
  }
}
```

Matching is case-insensitive substring matching against the alert's event text. When overriding, the *entire* default table is replaced — include every keyword you want matched.

## Testing Kurokku Devices

The `scripts/fake_alerts.py` tool pushes fake weather alerts directly to a kurokku device's Redis instance, bypassing the normal collection pipeline. Useful for verifying alert display timing, priority ordering, and scrolling behavior on LED clocks.

```bash
# Push a single Tornado Warning (priority 0) with 5 min TTL
uv run python scripts/fake_alerts.py --scenario tornado --redis-url redis://lcdtest.local:6379

# Push multiple alerts at different priority levels
uv run python scripts/fake_alerts.py --scenario mixed --redis-url redis://192.168.1.100

# Shorter TTL for quick iteration (2 minutes)
uv run python scripts/fake_alerts.py --scenario severe --ttl 120 --redis-url redis://lcdtest.local:6379

# Preview what would be written without touching Redis
uv run python scripts/fake_alerts.py --scenario all --dry-run

# Custom alert text
uv run python scripts/fake_alerts.py --scenario custom --event "Zombie Apocalypse Warning" --priority 0 --redis-url redis://lcdtest.local:6379

# Clear all test alerts from a device
uv run python scripts/fake_alerts.py --clear --redis-url redis://lcdtest.local:6379
```

**Built-in scenarios:**

| Scenario | Alerts | Priorities |
|----------|--------|------------|
| `tornado` | Tornado Warning | 0 |
| `severe` | Severe Thunderstorm Warning | 1 |
| `flood` | Flash Flood Warning | 1 |
| `heat` | Excessive Heat Warning | 2 |
| `winter` | Winter Storm Warning | 2 |
| `wind` | High Wind Warning | 2 |
| `fog` | Dense Fog Advisory | 3 |
| `frost` | Frost Advisory | 3 |
| `mixed` | Tornado + Severe Tstorm + Heat | 0, 1, 2 |
| `all` | One of each priority level | 0–5 |
| `custom` | Your text via `--event` | Your value via `--priority` |

The `--slug` flag defaults to `spring_hill_tn_noaa`. Override it to target a different location's key namespace.

## Code Quality

```bash
uv run ruff check .             # Lint
uv run ruff format .            # Format
uv run mypy app tests           # Type check
```

### Pre-commit

```bash
uv run pre-commit install       # Install the local Git hook
uv run pre-commit run --all-files
```

## Configuration

Copy `.env.example` to `.env` and edit as needed. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./nalssi.db` | Database connection |
| `DEFAULT_COLLECTION_INTERVAL` | `300` | Seconds between collections |
| `ENABLE_SCHEDULER` | `true` | Enable/disable background collection |
| `ALERT_PRIORITIES_FILE` | | YAML file overriding alert display priorities (merged over the bundled defaults) |
| `RADAR_ENABLED` | `true` | Collect radar imagery for US locations |
| `RADAR_STORAGE_DIR` | `./data/radar` | Where radar frames are cached on disk |
| `RADAR_RETENTION_MINUTES` | `120` | Radar history to keep (upstream offers ~2h max) |
| `RADAR_VIEW_SPAN_KM` | `240` | Width of each location's radar view |
| `RADAR_RANGE_RINGS_KM` | `50,100` | Distance rings drawn around the location (empty to disable) |
| `RADAR_GEOMET_URL` | MSC GeoMet | Canadian radar WMS endpoint |
| `RADAR_HYDRO_WMS_URL` | USGS hydro | Water shading for the basemap (empty to disable) |
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
├── scripts/
│   └── fake_alerts.py          # Push fake alerts to kurokku devices
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

MIT — see [LICENSE](LICENSE) for details.
