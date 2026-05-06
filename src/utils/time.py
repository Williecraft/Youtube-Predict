from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(s: str) -> datetime:
    """Parse UTC ISO 8601 string → timezone-aware datetime."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_iso(dt: datetime) -> str:
    """datetime → UTC ISO 8601 string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes_since(iso_str: str) -> float:
    """Minutes elapsed since an ISO 8601 timestamp."""
    return (now_utc() - parse_iso(iso_str)).total_seconds() / 60


def minutes_between(iso_a: str, iso_b: str) -> float:
    return (parse_iso(iso_b) - parse_iso(iso_a)).total_seconds() / 60
