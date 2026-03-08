.PHONY: dev test test-unit test-integration test-quick lint lint-fix format format-check check migrate migrate-new

# Dev server
dev:
	uv run uvicorn app.main:app --reload

# Testing
test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test-quick:
	uv run pytest --no-cov -q

# Linting & formatting
lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

# Run lint + format check + tests
check: lint format-check test

# Database migrations
migrate:
	uv run alembic upgrade head

migrate-new:
	@read -p "Migration message: " msg; uv run alembic revision --autogenerate -m "$$msg"
