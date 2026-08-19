"""
Tests for the radar feature gate.

With RADAR_ENABLED off, radar must be absent entirely — no routes, no nav item
— so a deployment focused on alerts and observations doesn't expose a
half-working section.

The flag is read at import time, so these run the app in a subprocess with the
environment set rather than trying to re-import it in place.
"""

import json
import subprocess
import sys

import pytest

_PROBE = """
import json, os, sys
sys.path.insert(0, {repo!r})
from app.main import app
from app.templating import templates

paths = sorted(
    r.path for r in app.routes if getattr(r, "path", "").startswith("/radar")
)
nav = templates.get_template("base.html").render(nav_active="dashboard")
print(json.dumps({{
    "radar_routes": paths,
    "nav_has_radar": 'href="/radar"' in nav,
}}))
"""


def _probe(repo_root, enabled: str) -> dict:
    """Import the app in a clean process with RADAR_ENABLED set."""
    env = {
        **dict(__import__("os").environ),
        "RADAR_ENABLED": enabled,
        "ENABLE_SCHEDULER": "false",
        "DATABASE_URL": "sqlite:///./test_gate.db",
    }
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(repo=str(repo_root))],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    parsed: dict = json.loads(result.stdout.strip().splitlines()[-1])
    return parsed


@pytest.fixture(scope="module")
def repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent.parent


@pytest.mark.integration
def test_radar_routes_exist_when_enabled(repo_root):
    result = _probe(repo_root, "true")

    assert result["radar_routes"], "expected radar routes to be registered"
    assert "/radar" in result["radar_routes"]
    assert result["nav_has_radar"] is True


@pytest.mark.integration
def test_radar_is_absent_when_disabled(repo_root):
    result = _probe(repo_root, "false")

    assert result["radar_routes"] == [], (
        f"radar routes leaked through the gate: {result['radar_routes']}"
    )
    assert result["nav_has_radar"] is False


@pytest.mark.integration
def test_disabling_radar_leaves_the_rest_of_the_app_intact(repo_root):
    """The gate must remove radar only, not break the app."""
    env = {
        **dict(__import__("os").environ),
        "RADAR_ENABLED": "false",
        "ENABLE_SCHEDULER": "false",
        "DATABASE_URL": "sqlite:///./test_gate.db",
    }
    probe = f"""
import sys
sys.path.insert(0, {str(repo_root)!r})
from app.main import app
paths = {{getattr(r, "path", "") for r in app.routes}}
assert "/health" in paths, paths
assert "/" in paths, paths
assert "/forecast" in paths, paths
assert "/alerts" in paths, paths
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
