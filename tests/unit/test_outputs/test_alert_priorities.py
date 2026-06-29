"""
Unit tests for the alert-priorities YAML loader and validation.
"""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.outputs.formats.alert_priorities import (
    AlertPriorityConfig,
    load_alert_priorities,
    load_effective_alert_priorities,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "priorities.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_bundled_file_loads_and_flattens():
    """The shipped default file loads, validates, and flattens cleanly."""
    config = load_alert_priorities()
    flat = config.flatten()

    # Spot-check representative entries across tiers.
    assert flat["tornado"] == 0
    assert flat["severe thunderstorm"] == 1
    assert flat["fire weather"] == 2
    assert flat["extreme heat"] == 3
    assert flat["excessive heat"] == 3
    assert flat["special weather"] == 4
    assert config.cap_fallback["unknown"] == 5


def test_flatten_lowercases_keywords(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          0: ["Tornado", "  Storm Surge  "]
        cap_fallback:
          unknown: 5
        """,
    )
    flat = load_alert_priorities(path).flatten()
    assert flat == {"tornado": 0, "storm surge": 0}


def test_priority_out_of_range_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          9: ["tornado"]
        cap_fallback:
          unknown: 5
        """,
    )
    with pytest.raises(ValidationError, match="out of range"):
        load_alert_priorities(path)


def test_duplicate_keyword_conflicting_priority_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          1: ["flood"]
          2: ["flood"]
        cap_fallback:
          unknown: 5
        """,
    )
    with pytest.raises(ValidationError, match="multiple priorities"):
        load_alert_priorities(path)


def test_empty_keyword_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          1: ["  "]
        cap_fallback:
          unknown: 5
        """,
    )
    with pytest.raises(ValidationError, match="must not be empty"):
        load_alert_priorities(path)


def test_cap_fallback_out_of_range_rejected(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          0: ["tornado"]
        cap_fallback:
          unknown: 9
        """,
    )
    with pytest.raises(ValidationError, match="out of range"):
        load_alert_priorities(path)


def test_same_keyword_same_priority_allowed():
    """A keyword repeated under the same priority is harmless."""
    config = AlertPriorityConfig(
        tiers={1: ["flood", "flood"]},
        cap_fallback={"unknown": 5},
    )
    assert config.flatten() == {"flood": 1}


def test_partial_override_file_validates(tmp_path: Path):
    """An override file may omit cap_fallback (or tiers) entirely."""
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          4: ["tornado"]
        """,
    )
    config = load_alert_priorities(path)
    assert config.flatten() == {"tornado": 4}
    assert config.cap_fallback == {}


# --- load_effective_alert_priorities (override layering) ---


def test_no_override_returns_bundled_defaults():
    priorities, cap = load_effective_alert_priorities(None)
    bundled = load_alert_priorities()
    assert priorities == bundled.flatten()
    assert cap == bundled.cap_fallback


def test_override_changes_existing_keyword_priority(tmp_path: Path):
    """An override moves a keyword to a different tier without touching others."""
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          4: ["tornado"]
        """,
    )
    priorities, cap = load_effective_alert_priorities(path)
    # Overridden keyword changed...
    assert priorities["tornado"] == 4
    # ...everything else preserved from the bundled defaults.
    bundled = load_alert_priorities().flatten()
    assert priorities["hurricane"] == bundled["hurricane"]
    assert priorities["extreme heat"] == bundled["extreme heat"]
    assert cap == load_alert_priorities().cap_fallback


def test_override_adds_new_keyword(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          2: ["dust storm"]
        """,
    )
    priorities, _ = load_effective_alert_priorities(path)
    assert priorities["dust storm"] == 2
    # Bundled defaults still present.
    assert priorities["tornado"] == 0


def test_override_only_cap_fallback(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        cap_fallback:
          moderate: 4
        """,
    )
    priorities, cap = load_effective_alert_priorities(path)
    assert cap["moderate"] == 4
    # Other severities untouched; keyword map unchanged.
    assert cap["extreme"] == 1
    assert priorities == load_alert_priorities().flatten()


def test_missing_override_file_falls_back_to_defaults(tmp_path: Path):
    missing = tmp_path / "does_not_exist.yaml"
    priorities, cap = load_effective_alert_priorities(missing)
    bundled = load_alert_priorities()
    assert priorities == bundled.flatten()
    assert cap == bundled.cap_fallback


def test_invalid_override_file_falls_back_to_defaults(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """
        tiers:
          99: ["tornado"]
        """,
    )
    priorities, cap = load_effective_alert_priorities(path)
    bundled = load_alert_priorities()
    # Invalid override ignored entirely; defaults preserved (tornado stays 0).
    assert priorities == bundled.flatten()
    assert cap == bundled.cap_fallback
