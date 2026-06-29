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
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = structlog.get_logger()

DEFAULT_PRIORITIES_FILE = Path(__file__).resolve().parent / "alert_priorities.yaml"

# Inclusive range of valid priority levels (0 = highest urgency).
MIN_PRIORITY = 0
MAX_PRIORITY = 5


class AlertPriorityConfig(BaseModel):
    """
    Validated representation of an alert-priorities YAML document.

    Both fields default to empty so an *override* file may be partial — listing
    only the keywords or CAP severities it wants to change. The bundled default
    file always provides both (guarded by tests).
    """

    tiers: dict[int, list[str]] = Field(default_factory=dict)
    cap_fallback: dict[str, int] = Field(default_factory=dict)

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


def load_effective_alert_priorities(
    override_path: str | Path | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Load the bundled defaults and apply an optional override file on top.

    The override file uses the same schema as the bundled file but may be
    partial: any keyword it lists wins over the default (including moving a
    keyword to a different priority tier), and any ``cap_fallback`` severity it
    lists overrides the default. Keywords and severities it does not mention are
    left untouched. (Removing a default keyword entirely is not supported — set
    it to a low priority instead.)

    If ``override_path`` is set but the file cannot be read or fails validation,
    the error is logged and the bundled defaults are used unchanged, so a bad
    override file never takes the service down.

    Args:
        override_path: Path to an override YAML file, or empty/None to use only
            the bundled defaults.

    Returns:
        ``(alert_priorities, cap_severity_priorities)`` as flattened dicts.
    """
    base = load_alert_priorities()
    priorities = base.flatten()
    cap_fallback = dict(base.cap_fallback)

    if not override_path:
        return priorities, cap_fallback

    try:
        override = load_alert_priorities(Path(override_path))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        logger.warning(
            "Failed to load alert priorities override %s; using bundled "
            "defaults instead: %s",
            override_path,
            exc,
        )
        return priorities, cap_fallback

    override_priorities = override.flatten()
    priorities.update(override_priorities)
    cap_fallback.update(override.cap_fallback)
    logger.info(
        "Applied alert priorities override from %s "
        "(%d keyword override(s), %d cap fallback override(s))",
        override_path,
        len(override_priorities),
        len(override.cap_fallback),
    )
    return priorities, cap_fallback
