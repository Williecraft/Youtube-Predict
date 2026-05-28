"""
爬蟲排程主入口。

使用方式：
  python -m src.crawler.run_scheduler

架構：
  主迴圈每 60 秒 tick 一次，每個 tick 依排程執行：
    - collect_trending        每 15 min
    - collect_from_search     每 60 min
    - collect_from_channels   每 60 min
    - static fetch            for newly discovered videos
    - timeseries snapshot     for due videos
    - comment snapshots       for videos in 0-3h window

多主機：
  每支影片用 acquire_lease() / release_lease() 保護，
  同一 video 同一時間只有一台主機在抓。
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.crawler.collect_video_list import (
    collect_explore,
    collect_from_channels,
    collect_from_fresh_search,
    collect_from_search,
    collect_from_shorts,
)
from src.crawler.fetch_comments import fetch_comments_snapshot
from src.crawler.fetch_static import fetch_static
from src.crawler.fetch_timeseries import fetch_timeseries_snapshot
from src.utils.http_client import YouTubeClient, set_stop as _http_set_stop
from src.utils.logging import get_logger, setup_file_logging, summary
from src.utils.state_db import StateDB
from src.utils.time import format_iso, now_utc, parse_iso

# ── paths ──────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_DB_PATH = _DATA_DIR / "state.db"
_LOG_DIR = _REPO_ROOT / "logs"

# ── intervals (seconds) ────────────────────────────────────────────────────
# Active discovery: only fresh_search (very recent uploads) and shorts_page.
# Explore / regular search / channel polling are disabled — see DISCOVERY_DISABLED.
_INTERVAL_FRESH_SEARCH_S = 5 * 60   # search "last hour" sort=new every 5 min, filter to ≤5 min
_INTERVAL_SHORTS_S = 5 * 60         # poll shorts home every 5 min (Shorts-only mode)
_TICK_S = 30

DISCOVERY_DISABLED = True           # explore/search/channel disabled — Shorts-only mode
FRESH_SEARCH_DISABLED = True        # fresh_search also disabled — only shorts_page

# Pause discovery (fresh_search + shorts) when overdue queue exceeds this.
# Speedup mode: throughput ~1200 events/hour ≈ 20/min. >300 overdue = 15+ min behind.
_AT_CAPACITY_THRESHOLD = 300

setup_file_logging(_LOG_DIR)
logger = get_logger("crawler.scheduler")

_running = True
_ctrl_c_count = 0


def _signal_handler(sig, frame):
    global _running, _ctrl_c_count
    _ctrl_c_count += 1
    if _ctrl_c_count == 1:
        summary.info("Ctrl+C — stopping after current task (press again to force quit)")
        _running = False
        _http_set_stop(True)
    else:
        summary.info("Force quit.")
        sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _ts_to_epoch(iso: str | None) -> float:
    if not iso:
        return 0.0
    try:
        return parse_iso(iso).timestamp()
    except Exception:
        return 0.0


def main():
    summary.info("Scheduler starting — data_dir=%s", _DATA_DIR)
    client = YouTubeClient()
    db = StateDB(_DB_PATH)

    while _running:
        now_ts = time.time()

        # ── discovery ──────────────────────────────────────────────────────
        # explore / regular search / channel polling are disabled by default.
        # Only fresh_search + shorts_page actively discover new videos now.
        if not DISCOVERY_DISABLED:
            if now_ts - db.job_last_run("explore") >= 15 * 60:
                try:
                    n = collect_explore(client, db)
                    db.job_mark_ran("explore")
                    db.log_event("explore", "ok", f"found {n} new videos")
                    summary.info("[explore] +%d new videos", n)
                except Exception as exc:
                    logger.exception("collect_explore error: %s", exc)
                    db.log_event("explore", "fail", str(exc))

            if now_ts - db.job_last_run("search") >= 60 * 60:
                try:
                    n = collect_from_search(client, db, _DATA_DIR)
                    db.job_mark_ran("search")
                    db.log_event("search", "ok", f"found {n} new videos")
                    summary.info("[search] +%d new videos", n)
                except Exception as exc:
                    logger.exception("collect_from_search error: %s", exc)
                    db.log_event("search", "fail", str(exc))

            if now_ts - db.job_last_run("channel") >= 10 * 60:
                try:
                    n = collect_from_channels(client, db)
                    db.job_mark_ran("channel")
                    db.log_event("channel", "ok", f"found {n} new videos")
                    summary.info("[channel] +%d new videos", n)
                except Exception as exc:
                    logger.exception("collect_from_channels error: %s", exc)
                    db.log_event("channel", "fail", str(exc))

        # Pause discovery when timeseries queue is backed up to avoid making it worse
        overdue = db.count_overdue_timeseries()
        at_capacity = overdue >= _AT_CAPACITY_THRESHOLD
        if at_capacity:
            summary.info("[discovery] paused — overdue=%d (threshold=%d)",
                         overdue, _AT_CAPACITY_THRESHOLD)

        if not at_capacity and now_ts - db.job_last_run("shorts_page") >= _INTERVAL_SHORTS_S:
            try:
                n = collect_from_shorts(client, db)
                db.job_mark_ran("shorts_page")
                db.log_event("shorts_page", "ok", f"found {n} new videos")
                summary.info("[shorts_page] +%d new videos", n)
            except Exception as exc:
                logger.exception("collect_from_shorts error: %s", exc)
                db.log_event("shorts_page", "fail", str(exc))
                summary.warning("[shorts_page] ERROR: %s", exc)

        if not FRESH_SEARCH_DISABLED and not at_capacity and now_ts - db.job_last_run("fresh_search") >= _INTERVAL_FRESH_SEARCH_S:
            try:
                n = collect_from_fresh_search(client, db, _DATA_DIR)
                db.job_mark_ran("fresh_search")
                db.log_event("fresh_search", "ok", f"found {n} new videos")
                summary.info("[fresh_search] +%d new videos", n)
            except Exception as exc:
                logger.exception("collect_from_fresh_search error: %s", exc)
                db.log_event("fresh_search", "fail", str(exc))
                summary.warning("[fresh_search] ERROR: %s", exc)

        # ── static fetch for new videos ────────────────────────────────────
        _run_static_fetches(client, db)

        # ── timeseries snapshots ───────────────────────────────────────────
        _run_timeseries(client, db)

        # ── comment snapshots ──────────────────────────────────────────────
        _run_comments(client, db)

        if _running:
            # sleep in chunks so Ctrl+C responds within ~0.5s
            end = time.monotonic() + _TICK_S
            while _running and time.monotonic() < end:
                time.sleep(0.5)

    summary.info("Scheduler stopped.")


_STATIC_MAX_ATTEMPTS = 3


def _mark_static_give_up_if_exhausted(db: StateDB, video_id: str) -> None:
    with db._conn() as conn:
        err_count = conn.execute(
            "SELECT COUNT(*) FROM crawl_errors WHERE video_id=? AND task='fetch_static'",
            (video_id,),
        ).fetchone()[0]
    if err_count >= _STATIC_MAX_ATTEMPTS:
        db.update_video(video_id, static_fetched=-1)
        logger.warning("fetch_static %s: giving up after %d failures", video_id, err_count)
        summary.warning("[static] gave up on %s after %d failures", video_id, err_count)


def _run_static_fetches(client: YouTubeClient, db: StateDB, batch: int = 5):
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT video_id, source FROM videos WHERE static_fetched=0 LIMIT ?", (batch,)
        ).fetchall()
    if rows:
        summary.info("[static] fetching %d pending videos", len(rows))

    for row in rows:
        video_id = row["video_id"]
        discovery_source = row["source"] or ""
        if not db.acquire_lease(video_id, seconds=120):
            continue
        try:
            result = fetch_static(client, video_id, _DATA_DIR, discovery_source)
            if result:
                publish_time = result.get("publish_time")
                db.update_video(video_id, static_fetched=1)
                if publish_time:
                    db.set_publish_time(video_id, publish_time)
                    db.schedule_next_timeseries(video_id, publish_time)
                db.log_event("static", "ok", result.get("video_status", ""), video_id)
            else:
                db.log_error(video_id, "fetch_static", "returned None")
                db.log_event("static", "fail", "returned None", video_id)
                _mark_static_give_up_if_exhausted(db, video_id)
        except Exception as exc:
            logger.exception("fetch_static %s error: %s", video_id, exc)
            db.log_error(video_id, "fetch_static", str(exc))
            db.log_event("static", "fail", str(exc), video_id)
            _mark_static_give_up_if_exhausted(db, video_id)
        finally:
            db.release_lease(video_id)
        client.jitter_sleep(0.8, 1.8)


def _run_timeseries(client: YouTubeClient, db: StateDB, batch: int = 40):
    due = db.get_due_timeseries(limit=batch)
    for row in due:
        video_id = row["video_id"]
        publish_time = row["publish_time"]
        if not db.acquire_lease(video_id, seconds=90):
            continue
        try:
            result = fetch_timeseries_snapshot(client, video_id, publish_time, _DATA_DIR)
            if result:
                video_status = result.get("video_status", "")
                if video_status in ("LOGIN_REQUIRED", "ERROR", "UNPLAYABLE"):
                    db.update_video(video_id, track_until=format_iso(now_utc()))
                    logger.info("stopping %s — status=%s", video_id, video_status)
                    db.log_event("timeseries", "skip", f"stopped: {video_status}", video_id)
                else:
                    db.schedule_next_timeseries(video_id, publish_time or "", row["next_ts_due"])
                    db.log_event("timeseries", "ok",
                                 f"views={result.get('view_count')}", video_id)
            else:
                db.log_error(video_id, "fetch_timeseries", "returned None")
                db.log_event("timeseries", "fail", "returned None", video_id)
                db.schedule_next_timeseries(video_id, publish_time or "", row["next_ts_due"])
        except Exception as exc:
            logger.exception("fetch_timeseries %s error: %s", video_id, exc)
            db.log_error(video_id, "fetch_timeseries", str(exc))
            db.log_event("timeseries", "fail", str(exc), video_id)
        finally:
            db.release_lease(video_id)
        client.jitter_sleep(0.5, 1.5)


def _run_comments(client: YouTubeClient, db: StateDB):
    due = db.get_due_comments()
    now = now_utc()

    for row in due:
        video_id = row["video_id"]
        publish_time = row["publish_time"]
        if not publish_time:
            continue

        try:
            pub = parse_iso(publish_time)
        except Exception:
            continue

        age_h = (now - pub).total_seconds() / 3600

        # determine which snapshots are still pending and within window
        for label, target_h, col in [("t1h", 1, "comment_t1h"), ("t2h", 2, "comment_t2h"), ("t3h", 3, "comment_t3h")]:
            if row[col] != 0:
                continue  # already done or missed

            # target window: [target_h - 0.2h, target_h + 0.2h] (±12 min)
            if not (target_h - 0.2 <= age_h <= target_h + 0.2):
                if age_h > target_h + 0.2:
                    # missed — mark skipped
                    db.mark_comment_done(video_id, label, done=False)
                continue

            if not db.acquire_lease(video_id, seconds=120):
                continue
            try:
                n = fetch_comments_snapshot(client, video_id, label, _DATA_DIR)
                db.mark_comment_done(video_id, label, done=True)
                logger.info("comments %s [%s]: %d saved", video_id, label, n)
                db.log_event("comments", "ok", f"{label}: {n} saved", video_id)
            except Exception as exc:
                logger.exception("fetch_comments %s [%s] error: %s", video_id, label, exc)
                db.log_error(video_id, f"fetch_comments_{label}", str(exc))
                db.log_event("comments", "fail", f"{label}: {exc}", video_id)
            finally:
                db.release_lease(video_id)
            client.jitter_sleep(1.0, 2.0)


if __name__ == "__main__":
    main()
