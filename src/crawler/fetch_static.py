"""
爬取影片靜態資料，同時更新 channel_static.json。

來源優先順序：
  1. InnerTube player endpoint → videoDetails (view count, title, channelId, duration, etc.)
  2. watch page ytInitialData  → category, tags, publishDate
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.crawler.detect_shorts import detect_shorts
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
    """
    Fetch and persist static info for one video.
    Updates data/raw/static/videos_static.json and channel_static.json.
    Returns the static dict, or None on failure.
    """
    static_path = data_dir / "raw" / "static" / "videos_static.json"
    channel_path = data_dir / "raw" / "static" / "channel_static.json"

    # ── 1. InnerTube player endpoint ──────────────────────────────────────
    player = client.post_innertube("player", {"videoId": video_id})
    if not player:
        logger.warning("fetch_static %s: player endpoint failed", video_id)
        return None

    video_details = player.get("videoDetails", {})
    playability = player.get("playabilityStatus", {})

    title = video_details.get("title", "")
    channel_id = video_details.get("channelId", "")
    channel_title = video_details.get("author", "")
    length_seconds = int(video_details.get("lengthSeconds") or 0)
    view_count = int(video_details.get("viewCount") or 0)
    video_status = playability.get("status", "UNKNOWN")  # OK / LOGIN_REQUIRED / UNPLAYABLE / ERROR

    # ── 2. watch page ytInitialData for extra metadata ────────────────────
    client.jitter_sleep(1.0, 2.5)
    init_data, init_player = client.get_watch_page(video_id)

    # publish_time from microformat
    microformat = dig(init_player, "microformat", "playerMicroformatRenderer")
    publish_time = (microformat or {}).get("publishDate") or (microformat or {}).get("uploadDate")

    # category
    category = (microformat or {}).get("category", "")

    # tags from videoDetails (player gives tags as well)
    tags: list[str] = video_details.get("keywords") or []
    tag_count = len(tags)

    # title_length
    title_length = len(title)

    # subscriber count from secondary info
    sub_text = dig(
        init_data,
        "contents", "twoColumnWatchNextResults", "results", "results",
        "contents", 1, "videoSecondaryInfoRenderer",
        "owner", "videoOwnerRenderer", "subscriberCountText", "simpleText",
    )
    subscriber_count = parse_count_text(sub_text)

    # ── 3. Shorts detection ────────────────────────────────────────────────
    client.jitter_sleep(0.5, 1.5)
    is_shorts_str, shorts_code = detect_shorts(client, video_id)
    is_shorts = is_shorts_str == "shorts"

    # ── assemble record ────────────────────────────────────────────────────
    fetched_at = format_iso(now_utc())
    record = {
        "video_id": video_id,
        "title": title,
        "title_length": title_length,
        "channel_id": channel_id,
        "publish_time": publish_time,
        "duration_seconds": length_seconds,
        "category": category,
        "tags": tags,
        "tag_count": tag_count,
        "is_shorts": is_shorts,
        "shorts_status_code": shorts_code,
        "shorts_checked_at": fetched_at,
        "view_count_at_fetch": view_count,
        "video_status": video_status,
        "static_fetched_at": fetched_at,
    }

    # ── persist videos_static.json ────────────────────────────────────────
    videos_static = load_json_dict(static_path)
    videos_static[video_id] = record
    save_json_dict(static_path, videos_static)
    logger.info("fetch_static %s: saved (shorts=%s, status=%s)", video_id, is_shorts, video_status)

    # ── persist channel_static.json ───────────────────────────────────────
    if channel_id:
        channels = load_json_dict(channel_path)
        if channel_id not in channels:
            channels[channel_id] = {
                "channel_id": channel_id,
                "channel_title": channel_title,
                "subscriber_count": subscriber_count,
                "subscriber_count_checked_at": fetched_at,
                "discovered_at": fetched_at,
                "discovered_via_video_id": video_id,
                "last_checked_at": fetched_at,
                "last_new_video_at": None,
            }
        else:
            # update subscriber count if we have a fresher number
            if subscriber_count is not None:
                channels[channel_id]["subscriber_count"] = subscriber_count
                channels[channel_id]["subscriber_count_checked_at"] = fetched_at
            channels[channel_id]["last_checked_at"] = fetched_at
        save_json_dict(channel_path, channels)

    return record
