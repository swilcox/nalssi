"""
Load and validate the alert-priority configuration.

The priority map that decides how prominently each weather alert is shown on
the LED clock lives in ``alert_priorities.yaml`` (data, not code) so it can be
reviewed, diffed, and corrected without a code change — for example when NWS
renames an event type. This module reads that file, validates it, and flattens
the tier groupings into the ``{event_substring: priority}`` mapping the format
transform expects.
"""

from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, field_validator

logger = structlog.get_logger()

DEFAULT_PRIORITIES_FILE = Path(__file__).resolve().parent / "alert_priorities.yaml"

# Inclusive range of valid priority levels (0 = highest urgency).
MIN_PRIORITY = 0
MAX_PRIORITY = 5


class AlertPriorityConfig(BaseModel):
    """Validated representation of an alert-priorities YAML document."""

    tiers: dict[int, list[str]]
    cap_fallback: dict[str, int]

    @field_validator("tiers")
    @classmethod
    def _validate_tiers(cls, tiers: dict[int, list[str]]) -> dict[int, list[str]]:
        seen: dict[str, int] = {}
        for priority, keywords in tiers.items():
            if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
                raise ValueError(
                    f"tier priority {priority} out of range "
                    f"[{MIN_PRIORITY}, {MAX_PRIORITY}]"
                )
            for keyword in keywords:
                key = keyword.strip().lower()
                if not key:
                    raise ValueError("alert keyword must not be empty")
                if key in seen and seen[key] != priority:
                    raise ValueError(
                        f"keyword {key!r} mapped to multiple priorities "
                        f"({seen[key]} and {priority})"
                    )
                seen[key] = priority
        return tiers

    @field_validator("cap_fallback")
    @classmethod
    def _validate_cap_fallback(cls, cap_fallback: dict[str, int]) -> dict[str, int]:
        for severity, priority in cap_fallback.items():
            if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
                raise ValueError(
                    f"cap_fallback severity {severity!r} priority {priority} "
                    f"out of range [{MIN_PRIORITY}, {MAX_PRIORITY}]"
                )
        return cap_fallback

    def flatten(self) -> dict[str, int]:
        """
        Flatten tier groupings into a ``{keyword: priority}`` map.

        Keywords are lowercased so lookups are case-insensitive. The validator
        guarantees no keyword appears under two different priorities.
        """
        flat: dict[str, int] = {}
        for priority, keywords in self.tiers.items():
            for keyword in keywords:
                flat[keyword.strip().lower()] = priority
        return flat


def load_alert_priorities(path: Path | None = None) -> AlertPriorityConfig:
    """
    Load and validate an alert-priorities YAML file.

    Args:
        path: Path to the YAML file; defaults to the bundled
            ``alert_priorities.yaml``.

    Returns:
        The validated configuration.

    Raises:
        ValidationError: if the file is structurally invalid.
        OSError / yaml.YAMLError: if the file cannot be read or parsed.
    """
    path = path or DEFAULT_PRIORITIES_FILE
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AlertPriorityConfig.model_validate(raw)
