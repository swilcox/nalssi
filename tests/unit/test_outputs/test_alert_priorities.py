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
