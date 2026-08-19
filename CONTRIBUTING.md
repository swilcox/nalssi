# Contributing to Nalssi

Thanks for helping out. This guide covers the local setup, the conventions the
CI enforces, how the test suite is structured, and where to plug in new
features. If you get stuck on *why* a piece of the system works the way it does,
start with the module docstrings — they explain the non-obvious design decisions.

## Environment

Nalssi uses [uv](https://docs.astral.sh/uv/) for everything.

```bash
uv sync                     # create .venv and install deps
uv run alembic upgrade head # create/upgrade the local SQLite database
uv run python -m app.server --reload   # dev server on http://localhost:8000
```

`Makefile` wraps the common commands:

| Command | Does |
|---|---|
| `make dev` | Run the reloadable dev server |
| `make test` | Run the full suite with coverage |
| `make test-quick` | Run tests without coverage |
| `make lint` / `make format` | Ruff lint / format |
| `make check` | Lint + format-check + test (what CI runs) |
| `make migrate` | `alembic upgrade head` |
| `make migrate-new` | Generate a new migration from a prompt |

The dev server is `app/server.py`, not the `uvicorn` line in the README — they're
equivalent, but `make dev` is what's wired to the Makefile.

## Code style

Style is enforced by [ruff](https://docs.astral.sh/ruff/) and is configured in
`[tool.ruff]` in `pyproject.toml` — don't fight it, just run it:

```bash
uv run ruff check --fix .   # auto-fixes what it can
uv run ruff format .        # format the rest
uv run mypy app tests       # type check
```

Worth knowing because the config is non-default:

- **`indent-width = 4`** and **`quote-style = "double"`** — matches the existing
  files, but differs from ruff's Black-compatible defaults, so copy the look of
  the file you're editing rather than reformatting from habit.
- **`E501` (line length) is ignored** — long lines are left as-is; the formatter
  does not wrap them. Prefer readable multi-line expressions over tight packing,
  but don't break lines just to hit 88.
- **`B008` is ignored** because `Depends(...)` in FastAPI route signatures
  triggers it as a false positive.
- **No code comments unless the task calls for them.** The existing comments
  exist to explain *why* (the alert-diffing logic, the radar time formats, the
  circuit breaker), not *what*. Add a comment only when the surrounding code's
  intent is non-obvious.

There are a few pre-existing lint issues that are out of scope unless your change
touches them: `app/services/collectors/weather_collector.py`, the
`app/api/routes/weather.py` route, and `tests/unit/test_weather_collector.py`.
Leave them alone.

## Testing

Convention is **TDD**: write a failing test first, then make it pass. Coverage
target is **80%+** (`--cov=app`, enforced in `pyproject.toml`).

The suite is split by markers (defined in `pyproject.toml`, enforced by
`--strict-markers`):

| Marker | Meaning |
|---|---|
| `unit` | Fast, isolated, no database |
| `integration` | Slower, exercises the DB / FastAPI client |
| `e2e` | Full workflow |
| `slow` | Significant runtime |

`pytest` runs in **`asyncio_mode = auto`**, so async test functions need no
decorator.

A few invariants the suite is built to protect — if your change touches these,
the tests will tell you:

- **Don't point tests at the real database.** `tests/conftest.py` sets
  `DATABASE_URL=sqlite:///./test_nalssi.db`, disables the scheduler, and a
  `verify_test_mode` fixture hard-fails if a prod DB path slips in. New
  fixtures that open a real store will break this on purpose.
- **"Unknown = None, leave existing state alone."** Throughout the collector and
  output backends, `alerts=None` and `precipitation=None` mean *the lookup
  failed or the feature is off*, which is different from `[]` / `False`
  (*confirmed none*). Backends must therefore **preserve** existing state when
  they see `None` rather than overwrite it. Tests in
  `tests/unit/test_precipitation_distribution.py` and the Redis output tests
  guard this. Preserve it when you extend anything in that path.
- **The autouse `_no_radar_lookups_in_weather_collection` fixture** keeps the
  weather collector from making a live radar call during collection tests. If a
  test genuinely needs the lookup, patch the module attribute inside its own
  `with`/`monkeypatch` block — it takes precedence over the autouse fixture.

Run a single file or test the usual way:

```bash
uv run pytest tests/unit/test_weather_apis -q
uv run pytest -m unit
```

## Database migrations

Schema changes go through [Alembic] (`app/migrations/`). Autogenerate, then
review:

```bash
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head   # verify it applies cleanly
```

Two things to watch when the diff comes back:

- **Strip the false UUID↔NUMERIC noise.** Autogenerate on SQLite constantly
  emits spurious type-change operations for UUID columns. Delete ops that only
  toggle a `NUMERIC`/`UUID` type — they're not real changes.
- **Always write a `downgrade`.** Every migration in `app/migrations/versions/`
  is reversible; keep that true so `alembic downgrade` keeps working.

New models must be imported into `app/migrations/env.py`'s model import line, or
autogenerate won't see them.

## Extension points

nalssi is built around small, well-defined interfaces, so most new features are a
data change plus one file.

### A new weather API provider

1. Subclass `BaseWeatherClient` (`app/services/weather_apis/base.py`) and
   implement `get_current_weather`, `get_alerts`, and `get_forecast`, returning
   the normalized `WeatherData` / `WeatherAlert` / `ForecastPeriod` dataclasses.
   Normalize into the common shape — Celsius, m/s, hPa, UTC timestamps — the way
   `open_meteo.py` and `noaa.py` do.
2. Instantiate it in `WeatherCollector.__init__`
   (`app/services/collectors/weather_collector.py`).
3. Wire selection into `_get_client_for_location`, which maps `preferred_api` /
   `country_code` to a client. The current fallback is: explicit `preferred_api`
   wins, then `country_code == "US"` → NOAA, else Open-Meteo.
4. Add a fixtures JSON under `tests/fixtures/` and unit tests that parse a
   captured response.

### A new output backend

1. Subclass `BaseOutputBackend` (`app/services/outputs/base.py`) and implement
   `write`, `test_connection`, and optionally `close`. Honor the
   `None`-means-preserve contract on `alerts` and `precipitation`.
2. Register it in `BACKEND_CLASSES` in
   `app/services/outputs/manager.py`. The manager handles timeouts, the circuit
   breaker, location filtering, and concurrency — you don't re-implement those.

### A new Redis format transform

1. Subclass the transform pattern in
   `app/services/outputs/formats/kurokku.py` — each formatter yields
   `(key, value, ttl)` tuples and may yield none to skip a field.
2. Register it in `FORMAT_TRANSFORMS` in `redis_backend.py`.

### A new radar source

Mostly a data change in `app/services/imagery/radar.py` — see
`docs/international-weather-services.md` for the full walkthrough. Add a
`RadarSource` to `SOURCES`; if the service advertises its time dimension in a
form neither handled today (an explicit list or an ISO interval), extend
`RadarClient._parse_time_dimension`. The bbox math, storage, retention, and
viewer are source-agnostic and need no changes.

## CI

`.github/workflows/ci.yml` runs the full gate on PRs and pushes to `main` across
Python 3.11 and 3.12. It executes, in order:

1. `ruff format --check .`
2. `ruff check .`
3. `mypy app tests`
4. `pytest`

`make check` reproduces the format/lint/test portion locally; run
  `uv run mypy app tests` separately to cover the type-check step.

## Commits and pull requests

- **Conventional commits.** The log uses `feat:`, `fix:`, `refactor:`, `chore:`,
  and `ci:` with a short imperative subject, e.g.
  `fix: map Extreme Heat Watch/Warning to correct priorities`.
- **One concern per commit.** Keep migration, code, and `version` bump in
  separate commits — releases are `chore: bump version to X.Y.Z` commits that tag
  `vX.Y.Z`.
- **Bump `version` in `pyproject.toml`** when a fix or feature ships; it flows
  into `settings.APP_VERSION` and the NOAA `User-Agent`.
- **Run `uv run ruff check --fix . && uv run ruff format .`** before committing;
  the same four checks run as pre-commit hooks
  (`.pre-commit-config.yaml`). Install them once with
  `uv run pre-commit install`.
- **Add or update tests** for the change, and keep coverage above 80%.

## Troubleshooting

- **`uv: command not found`** — install uv, or use a venv with `pip`/`pipx`.
- **Tests use the production DB** — a `verify_test_mode` RuntimeError means a
  fixture overrode `DATABASE_URL`; check `tests/conftest.py`.
- **A new backend never fires** — confirm it's `enabled`, that its
  `location_filter` matches at least one location, and that the circuit breaker
  hasn't tripped (3 consecutive failures, 300s cooldown; see
  `app/services/outputs/manager.py`).
- **Radar nav item missing** — `RADAR_ENABLED` is `false`; the route group and
  nav item are fully gated off, by design.
