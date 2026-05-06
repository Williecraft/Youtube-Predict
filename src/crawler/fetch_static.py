"""
爬取影片靜態資料，同時更新 channel_static.json。
來源：GET /watch?v={id} → ytInitialData + ytInitialPlayerResponse
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.crawler.detect_shorts import detect_shorts
from src.crawler.fetch_timeseries import _parse_comment_count, _parse_subscriber_count
from src.utils.http_client import YouTubeClient, dig, parse_count_text
from src.utils.io import load_json_dict, save_json_dict
from src.utils.time import format_iso, now_utc

logger = logging.getLogger(__name__)

_ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_iso_duration(s: str | None) -> int | None:
    if not s:
        return None
    m = _ISO_DURATION_RE.match(s)
    if not m:
        return None
    h, mn, sc = (int(x or 0) for x in m.groups())
    return h * 3600 + mn * 60 + sc


def fetch_static(client: YouTubeClient, video_id: str, data_dir: Path) -> dict | None:
    static_path = data_dir / "raw" / "static" / "videos_static.json"
    channel_path = data_dir / "raw" / "static" / "channel_static.json"

    init_data, init_player = client.get_watch_page(video_id)
    if not init_player:
        logger.warning("fetch_static %s: watch page returned nothing", video_id)
        return None

    # ── videoDetails (from ytInitialPlayerResponse) ───────────────────────
    vd = init_player.get("videoDetails", {})
    title         = vd.get("title", "")
    channel_id    = vd.get("channelId", "")
    channel_title = vd.get("author", "")
    length_s      = int(vd.get("lengthSeconds") or 0)
    tags          = vd.get("keywords") or []
    video_status  = dig(init_player, "playabilityStatus", "status") or "UNKNOWN"

    # ── microformat (publish_time, category) ─────────────────────────────
    mf = dig(init_player, "microformat", "playerMicroformatRenderer") or {}
    publish_time = mf.get("publishDate") or mf.get("uploadDate")
    category     = mf.get("category", "")

    subscriber_count = _parse_subscriber_count(init_data)
    comment_count    = _parse_comment_count(init_data)

    # ── Shorts detection ──────────────────────────────────────────────────
    client.jitter_sleep(0.5, 1.5)
    is_shorts_str, shorts_code = detect_shorts(client, video_id)
    is_shorts = is_shorts_str == "shorts"

    fetched_at = format_iso(now_utc())
    record = {
        "video_id":                     video_id,
        "title":                        title,
        "title_length":                 len(title),
        "channel_id":                   channel_id,
        "publish_time":                 publish_time,
        "duration_seconds":             length_s,
        "category":                     category,
        "tags":                         tags,
        "tag_count":                    len(tags),
        "is_shorts":                    is_shorts,
        "shorts_status_code":           shorts_code,
        "shorts_checked_at":            fetched_at,
        "subscriber_count_at_fetch":    subscriber_count,
        "comment_count_at_fetch":       comment_count,
        "video_status":                 video_status,
        "static_fetched_at":            fetched_at,
    }

    videos_static = load_json_dict(static_path)
    videos_static[video_id] = record
    save_json_dict(static_path, videos_static)
    logger.info("fetch_static %s: saved (shorts=%s status=%s)", video_id, is_shorts, video_status)

    # ── channel_static.json ───────────────────────────────────────────────
    if channel_id:
        channels = load_json_dict(channel_path)
        if channel_id not in channels:
            channels[channel_id] = {
                "channel_id":                   channel_id,
                "channel_title":                channel_title,
                "subscriber_count":             subscriber_count,
                "subscriber_count_checked_at":  fetched_at,
                "discovered_at":                fetched_at,
                "discovered_via_video_id":      video_id,
                "last_checked_at":              fetched_at,
                "last_new_video_at":            None,
            }
        else:
            if subscriber_count is not None:
                channels[channel_id]["subscriber_count"] = subscriber_count
                channels[channel_id]["subscriber_count_checked_at"] = fetched_at
            channels[channel_id]["last_checked_at"] = fetched_at
        save_json_dict(channel_path, channels)

    return record
