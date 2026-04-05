#!/usr/bin/env python
"""
Push fake weather alerts to Redis in kurokuu format for testing.

Usage:
    uv run python scripts/fake_alerts.py [--scenario SCENARIO] [--slug SLUG] [--ttl SECONDS] [--clear]

Scenarios:
    tornado     - Tornado Warning (priority 0, highest)
    severe      - Severe Thunderstorm Warning (priority 1)
    flood       - Flash Flood Warning (priority 1)
    heat        - Excessive Heat Warning (priority 2)
    winter      - Winter Storm Warning (priority 2)
    wind        - High Wind Warning (priority 2)
    fog         - Dense Fog Advisory (priority 3)
    frost       - Frost Advisory (priority 3)
    mixed       - Multiple alerts at once (tornado + severe tstorm + heat)
    all         - One of every priority level (0-5)
    custom      - Provide --event and --priority manually

Examples:
    uv run python scripts/fake_alerts.py --scenario tornado
    uv run python scripts/fake_alerts.py --scenario mixed --ttl 120
    uv run python scripts/fake_alerts.py --scenario custom --event "Alien Invasion Warning" --priority 0 --ttl 60
    uv run python scripts/fake_alerts.py --duration-base 5.0 --duration-per-char 0.5 --scenario tornado
    uv run python scripts/fake_alerts.py --clear
"""

import argparse
import json
import sys
from datetime import UTC, datetime

import redis

# Kurokuu format constants
DISPLAY_DURATION_BASE = 3.0
DISPLAY_DURATION_PER_CHAR = 0.3

SCENARIOS = {
    "tornado": [
        {"event": "Tornado Warning", "priority": 0},
    ],
    "severe": [
        {"event": "Severe Thunderstorm Warning", "priority": 1},
    ],
    "flood": [
        {"event": "Flash Flood Warning", "priority": 1},
    ],
    "heat": [
        {"event": "Excessive Heat Warning", "priority": 2},
    ],
    "winter": [
        {"event": "Winter Storm Warning", "priority": 2},
    ],
    "wind": [
        {"event": "High Wind Warning", "priority": 2},
    ],
    "fog": [
        {"event": "Dense Fog Advisory", "priority": 3},
    ],
    "frost": [
        {"event": "Frost Advisory", "priority": 3},
    ],
    "mixed": [
        {"event": "Tornado Warning", "priority": 0},
        {"event": "Severe Thunderstorm Warning", "priority": 1},
        {"event": "Excessive Heat Warning", "priority": 2},
    ],
    "all": [
        {"event": "Tornado Warning", "priority": 0},
        {"event": "Flash Flood Warning", "priority": 1},
        {"event": "High Wind Warning", "priority": 2},
        {"event": "Dense Fog Advisory", "priority": 3},
        {"event": "Winter Weather Advisory", "priority": 4},
        {"event": "Special Weather Statement", "priority": 5},
    ],
}

DEFAULT_SLUG = "spring_hill_tn_noaa"
DEFAULT_TTL = 300  # 5 minutes
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def calc_display_duration(message: str, base: float = DISPLAY_DURATION_BASE, per_char: float = DISPLAY_DURATION_PER_CHAR) -> str:
    duration = len(message) * per_char + base
    return f"{round(duration, 1)}s"


def build_alert_entry(event: str, priority: int, ttl: int, slug: str, index: int, duration_base: float = DISPLAY_DURATION_BASE, duration_per_char: float = DISPLAY_DURATION_PER_CHAR):
    now = datetime.now(UTC)
    key = f"kurokku:alert:weather:{slug}:{index}"
    value = json.dumps({
        "timestamp": now.isoformat(),
        "message": event,
        "priority": priority,
        "display_duration": calc_display_duration(event, duration_base, duration_per_char),
        "delete_after_display": False,
    })
    return key, value, ttl


def clear_alerts(client: redis.Redis, slug: str):
    pattern = f"kurokku:alert:weather:{slug}:*"
    deleted = 0
    for key in client.scan_iter(match=pattern):
        client.delete(key)
        deleted += 1
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Push fake alerts to Redis for kurokuu testing")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()) + ["custom"], default="severe",
                        help="Alert scenario to push (default: severe)")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help=f"Location slug (default: {DEFAULT_SLUG})")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL, help=f"Alert TTL in seconds (default: {DEFAULT_TTL})")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL, help=f"Redis URL (default: {DEFAULT_REDIS_URL})")
    parser.add_argument("--clear", action="store_true", help="Clear all fake alerts for the slug and exit")
    parser.add_argument("--event", help="Custom event text (use with --scenario custom)")
    parser.add_argument("--priority", type=int, default=5, help="Custom priority 0-5 (use with --scenario custom)")
    parser.add_argument("--duration-base", type=float, default=DISPLAY_DURATION_BASE,
                        help=f"Display duration base in seconds (default: {DISPLAY_DURATION_BASE})")
    parser.add_argument("--duration-per-char", type=float, default=DISPLAY_DURATION_PER_CHAR,
                        help=f"Display duration per character in seconds (default: {DISPLAY_DURATION_PER_CHAR})")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without connecting to Redis")

    args = parser.parse_args()

    # Build alert list
    if args.scenario == "custom":
        if not args.event:
            print("Error: --event is required with --scenario custom", file=sys.stderr)
            sys.exit(1)
        alerts = [{"event": args.event, "priority": args.priority}]
    else:
        alerts = SCENARIOS[args.scenario]

    # Dry run mode
    if args.dry_run:
        if args.clear:
            print(f"Would clear: kurokku:alert:weather:{args.slug}:*")
            return

        print(f"Would write {len(alerts)} alert(s) to {args.redis_url}:\n")
        for i, alert in enumerate(alerts):
            key, value, ttl = build_alert_entry(alert["event"], alert["priority"], args.ttl, args.slug, i, args.duration_base, args.duration_per_char)
            parsed = json.loads(value)
            print(f"  Key: {key}")
            print(f"  TTL: {ttl}s")
            print(f"  Value: {json.dumps(parsed, indent=4)}")
            print()
        return

    # Connect to Redis
    try:
        client = redis.from_url(args.redis_url, decode_responses=True)
        client.ping()
    except redis.ConnectionError as e:
        print(f"Error: Cannot connect to Redis at {args.redis_url}: {e}", file=sys.stderr)
        sys.exit(1)

    # Clear mode
    if args.clear:
        deleted = clear_alerts(client, args.slug)
        print(f"Cleared {deleted} alert key(s) for slug '{args.slug}'")
        return

    # Clear existing alerts first, then write new ones
    cleared = clear_alerts(client, args.slug)
    if cleared:
        print(f"Cleared {cleared} existing alert key(s)")

    # Write alerts
    for i, alert in enumerate(alerts):
        key, value, ttl = build_alert_entry(alert["event"], alert["priority"], args.ttl, args.slug, i, args.duration_base, args.duration_per_char)
        client.set(key, value, ex=ttl)
        parsed = json.loads(value)
        print(f"Wrote: {key}  (TTL={ttl}s, priority={parsed['priority']}, duration={parsed['display_duration']})")

    print(f"\nDone! {len(alerts)} alert(s) written. They will expire in {args.ttl}s.")


if __name__ == "__main__":
    main()
