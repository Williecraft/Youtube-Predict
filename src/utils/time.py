from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


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


# ── relative-time parsing for comments (zh-TW / zh-CN / en) ────────────────

_REL_UNITS_SEC = {
    # zh
    "秒": 1, "分鐘": 60, "分钟": 60, "分": 60,
    "小時": 3600, "小时": 3600, "時": 3600,
    "天": 86400, "日": 86400,
    "週": 604800, "周": 604800, "星期": 604800,
    "個月": 2592000, "个月": 2592000, "月": 2592000,
    "年": 31536000,
    # en (singular & plural folded by stripping trailing "s")
    "second": 1, "minute": 60, "hour": 3600, "day": 86400,
    "week": 604800, "month": 2592000, "year": 31536000,
}

_REL_RE_ZH  = re.compile(r"(\d+)\s*(秒|分鐘|分钟|分|小時|小时|時|天|日|週|周|星期|個月|个月|月|年)")
_REL_RE_EN  = re.compile(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago", re.IGNORECASE)
_JUST_NOW_RE = re.compile(r"剛剛|刚刚|just now", re.IGNORECASE)


def parse_relative_time(text: str | None, reference: datetime | None = None) -> datetime | None:
    """
    Parse YouTube comment relative-time string (e.g. "3 分鐘前", "5 hours ago", "剛剛")
    to an absolute datetime, anchored at `reference` (default: now_utc).

    Returns None if unparseable. Result is approximate — YouTube only exposes
    coarse relative timestamps, so callers should treat this as best-effort.
    """
    if not text:
        return None
    ref = reference or now_utc()

    if _JUST_NOW_RE.search(text):
        return ref

    m = _REL_RE_ZH.search(text)
    if not m:
        m = _REL_RE_EN.search(text)
    if not m:
        return None

    n = int(m.group(1))
    unit = m.group(2).lower()
    seconds = _REL_UNITS_SEC.get(unit)
    if seconds is None:
        return None
    return ref - timedelta(seconds=n * seconds)
