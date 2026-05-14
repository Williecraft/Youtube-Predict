"""
SQLite-backed state store for the crawler scheduler.

Schema
------
videos          - one row per video_id; tracks crawl progress and scheduling
channels        - tracked channels discovered from collected videos
crawl_errors    - failed tasks for later retry
scheduler_jobs  - last_run_at per named job; survives restarts
crawl_log       - human-readable record of every major crawl event

Multi-host safety
-----------------
WAL mode allows concurrent readers + one writer. The `lease_until` + `lease_by`
columns let multiple hosts claim videos without overlap: a host atomically sets
lease_until = now+60s, then crawls; competing hosts skip any video with an
active lease that isn't theirs.
"""

from __future__ import annotations

import socket
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.utils.time import format_iso, now_utc, parse_iso

_HOST_ID = socket.gethostname()

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS videos (
    video_id            TEXT PRIMARY KEY,
    source              TEXT,
    source_detail       TEXT,
    discovered_at       TEXT,
    publish_time        TEXT,
    age_at_discovery_m  REAL,
    last_seen_at        TEXT,

    -- static fetch
    static_fetched      INTEGER DEFAULT 0,
    shorts_checked      INTEGER DEFAULT 0,

    -- timeseries scheduling
    track_until         TEXT,
    next_ts_due         TEXT,

    -- comment snapshots (0=pending, 1=done, -1=missed/skipped)
    comment_t1h         INTEGER DEFAULT 0,
    comment_t2h         INTEGER DEFAULT 0,
    comment_t3h         INTEGER DEFAULT 0,

    -- multi-host lease
    lease_until         TEXT,
    lease_by            TEXT
);

CREATE TABLE IF NOT EXISTS channels (
    channel_id                  TEXT PRIMARY KEY,
    channel_title               TEXT,
    subscriber_count            INTEGER,
    subscriber_count_checked_at TEXT,
    country                     TEXT,
    discovered_at               TEXT,
    discovered_via_video_id     TEXT,
    last_checked_at             TEXT,
    last_new_video_at           TEXT
);

CREATE TABLE IF NOT EXISTS crawl_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id    TEXT,
    task        TEXT,
    error_msg   TEXT,
    failed_at   TEXT,
    retry_after TEXT
);

CREATE TABLE IF NOT EXISTS scheduler_jobs (
    job_name    TEXT PRIMARY KEY,
    last_run_at TEXT,           -- UTC ISO 8601；NULL = 從未跑過
    last_host   TEXT            -- 哪台主機跑的
);

CREATE TABLE IF NOT EXISTS crawl_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time  TEXT,           -- UTC ISO 8601
    host        TEXT,
    job_name    TEXT,           -- e.g. "trending", "search", "timeseries", "static"
    video_id    TEXT,           -- NULL for job-level events
    status      TEXT,           -- "ok" / "fail" / "skip"
    detail      TEXT            -- 簡短說明，e.g. "found 42 videos" / error message
);
"""


class StateDB:
    def __init__(self, db_path: Path | str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ── video CRUD ─────────────────────────────────────────────────────────

    def add_video(
        self,
        video_id: str,
        source: str,
        source_detail: str,
        discovered_at: str,
        publish_time: str | None = None,
    ) -> bool:
        """Insert a new video. Returns True if inserted, False if already exists."""
        age = None
        if publish_time:
            try:
                age = (parse_iso(discovered_at) - parse_iso(publish_time)).total_seconds() / 60
            except Exception:
                pass

        track_until = None
        if publish_time:
            try:
                track_until = format_iso(parse_iso(publish_time) + timedelta(hours=72))
            except Exception:
                pass

        with self._conn() as conn:
            existing = conn.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,)).fetchone()
            if existing:
                # update last_seen_at
                conn.execute(
                    "UPDATE videos SET last_seen_at=? WHERE video_id=?",
                    (discovered_at, video_id),
                )
                return False
            conn.execute(
                """INSERT INTO videos
                   (video_id, source, source_detail, discovered_at, publish_time,
                    age_at_discovery_m, last_seen_at, track_until, next_ts_due)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (video_id, source, source_detail, discovered_at, publish_time,
                 age, discovered_at, track_until, discovered_at),
            )
        return True

    def get_video(self, video_id: str) -> sqlite3.Row | None:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()

    def update_video(self, video_id: str, **kwargs):
        if not kwargs:
            return
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [video_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE videos SET {sets} WHERE video_id=?", vals)

    def set_publish_time(self, video_id: str, publish_time: str):
        track_until = format_iso(parse_iso(publish_time) + timedelta(hours=72))
        self.update_video(video_id, publish_time=publish_time, track_until=track_until)

    # ── timeseries scheduling ──────────────────────────────────────────────

    def get_due_timeseries(self, limit: int = 50) -> list[sqlite3.Row]:
        """Videos whose next_ts_due has passed and tracking period hasn't ended."""
        now = format_iso(now_utc())
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM videos
                   WHERE next_ts_due <= ?
                     AND (track_until IS NULL OR track_until > ?)
                     AND static_fetched = 1
                     AND (lease_until IS NULL OR lease_until < ? OR lease_by = ?)
                   ORDER BY next_ts_due
                   LIMIT ?""",
                (now, now, now, _HOST_ID, limit),
            ).fetchall()
        return rows

    def count_overdue_timeseries(self) -> int:
        """Count videos whose next_ts_due has passed (proxy for queue backlog)."""
        now = format_iso(now_utc())
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM videos
                   WHERE next_ts_due <= ?
                     AND (track_until IS NULL OR track_until > ?)
                     AND static_fetched = 1""",
                (now, now),
            ).fetchone()
        return row[0] if row else 0

    def schedule_next_timeseries(self, video_id: str, publish_time: str, last_due: str | None = None):
        """Compute and set next_ts_due based on video age.

        Schedules relative to last_due (not now) so interval drift doesn't accumulate.
        If last_due is missing or more than one interval behind, falls back to now.
        """
        now = now_utc()
        try:
            pub = parse_iso(publish_time)
        except Exception:
            pub = now

        age_h = (now - pub).total_seconds() / 3600

        if age_h < 3:
            interval_m = 10
        elif age_h < 72:
            interval_m = 120
        else:
            interval_m = 360

        # Anchor to the last scheduled time so drift doesn't accumulate.
        # If last_due is stale (> 1 interval behind), fall back to now.
        try:
            base = parse_iso(last_due) if last_due else now
        except Exception:
            base = now
        candidate = base + timedelta(minutes=interval_m)
        if candidate < now:
            candidate = now + timedelta(minutes=interval_m)

        self.update_video(video_id, next_ts_due=format_iso(candidate))

    # ── comment snapshot scheduling ────────────────────────────────────────

    def get_due_comments(self) -> list[sqlite3.Row]:
        """Videos that need one or more comment snapshots, still within 0-3h window."""
        now = format_iso(now_utc())
        with self._conn() as conn:
            # comment snapshots must be done within 3h of publish
            return conn.execute(
                """SELECT * FROM videos
                   WHERE publish_time IS NOT NULL
                     AND (comment_t1h = 0 OR comment_t2h = 0 OR comment_t3h = 0)
                     AND static_fetched = 1
                     AND (lease_until IS NULL OR lease_until < ? OR lease_by = ?)
                   ORDER BY publish_time""",
                (now, _HOST_ID),
            ).fetchall()

    def mark_comment_done(self, video_id: str, label: str, done: bool = True):
        col = {"t1h": "comment_t1h", "t2h": "comment_t2h", "t3h": "comment_t3h"}.get(label)
        if col:
            self.update_video(video_id, **{col: 1 if done else -1})

    # ── channel CRUD ───────────────────────────────────────────────────────

    def upsert_channel(self, channel_id: str, **kwargs):
        with self._conn() as conn:
            existing = conn.execute("SELECT 1 FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
            if existing:
                if kwargs:
                    sets = ", ".join(f"{k}=?" for k in kwargs)
                    conn.execute(f"UPDATE channels SET {sets} WHERE channel_id=?", list(kwargs.values()) + [channel_id])
            else:
                cols = ["channel_id"] + list(kwargs.keys())
                vals = [channel_id] + list(kwargs.values())
                placeholders = ",".join("?" * len(cols))
                conn.execute(f"INSERT INTO channels ({','.join(cols)}) VALUES ({placeholders})", vals)

    def get_tracked_channels(self) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM channels ORDER BY last_new_video_at DESC NULLS LAST").fetchall()

    # ── lease (multi-host) ─────────────────────────────────────────────────

    def acquire_lease(self, video_id: str, seconds: int = 120) -> bool:
        """Try to claim a video for this host. Returns True if successful."""
        now = now_utc()
        now_s = format_iso(now)
        until_s = format_iso(now + timedelta(seconds=seconds))
        with self._conn() as conn:
            row = conn.execute("SELECT lease_until, lease_by FROM videos WHERE video_id=?", (video_id,)).fetchone()
            if row is None:
                return False
            lease_until, lease_by = row["lease_until"], row["lease_by"]
            if lease_until and lease_by != _HOST_ID:
                try:
                    if parse_iso(lease_until) > now:
                        return False
                except Exception:
                    pass
            conn.execute(
                "UPDATE videos SET lease_until=?, lease_by=? WHERE video_id=?",
                (until_s, _HOST_ID, video_id),
            )
        return True

    def release_lease(self, video_id: str):
        self.update_video(video_id, lease_until=None, lease_by=None)

    # ── scheduler job timing (survives restarts) ───────────────────────────

    def job_last_run(self, job_name: str) -> float:
        """Return the last run time of a job as a Unix timestamp (0 if never run)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_run_at FROM scheduler_jobs WHERE job_name=?", (job_name,)
            ).fetchone()
        if row and row["last_run_at"]:
            try:
                return parse_iso(row["last_run_at"]).timestamp()
            except Exception:
                pass
        return 0.0

    def job_mark_ran(self, job_name: str):
        """Record that a job just finished successfully."""
        now_s = format_iso(now_utc())
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO scheduler_jobs (job_name, last_run_at, last_host)
                   VALUES (?, ?, ?)
                   ON CONFLICT(job_name) DO UPDATE SET last_run_at=excluded.last_run_at,
                                                       last_host=excluded.last_host""",
                (job_name, now_s, _HOST_ID),
            )

    # ── crawl log ──────────────────────────────────────────────────────────

    def log_event(
        self,
        job_name: str,
        status: str,
        detail: str = "",
        video_id: str | None = None,
    ):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO crawl_log (event_time, host, job_name, video_id, status, detail)
                   VALUES (?,?,?,?,?,?)""",
                (format_iso(now_utc()), _HOST_ID, job_name, video_id, status, detail),
            )

    # ── errors ─────────────────────────────────────────────────────────────

    def log_error(self, video_id: str | None, task: str, msg: str, retry_after_s: int = 300):
        retry = format_iso(now_utc() + timedelta(seconds=retry_after_s))
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO crawl_errors (video_id, task, error_msg, failed_at, retry_after) VALUES (?,?,?,?,?)",
                (video_id, task, msg, format_iso(now_utc()), retry),
            )
