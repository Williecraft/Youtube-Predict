"""
爬取一支影片的當前時序快照。
來源：GET /watch?v={id} → ytInitialData + ytInitialPlayerResponse（一次請求拿全部）
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.utils.http_client import YouTubeClient, dig, parse_count_text
from src.utils.io import append_csv_row
from src.utils.time import format_iso, minutes_between, now_utc

logger = logging.getLogger(__name__)

_TS_FIELDS = [
    "video_id", "crawl_time", "time_since_publish_minutes",
    "view_count", "like_count", "comment_count",
    "subscriber_count", "video_status",
]


def fetch_timeseries_snapshot(
    client: YouTubeClient,
    video_id: str,
    publish_time: str | None,
    data_dir: Path,
) -> dict | None:
    crawl_time = format_iso(now_utc())

    init_data, init_player = client.get_watch_page(video_id)
    if not init_player:
        logger.warning("fetch_timeseries %s: watch page returned nothing", video_id)
        return None

    # view count & status — exact values from ytInitialPlayerResponse
    vd = init_player.get("videoDetails", {})
    view_raw = vd.get("viewCount")
    view_count = int(view_raw) if view_raw and str(view_raw).isdigit() else None
    video_status = dig(init_player, "playabilityStatus", "status") or "UNKNOWN"

    # engagement counts from ytInitialData (approximate)
    like_count       = _parse_like_count(init_data)
    comment_count    = _parse_comment_count(init_data)
    subscriber_count = _parse_subscriber_count(init_data)

    time_since = None
    if publish_time:
        try:
            time_since = round(minutes_between(publish_time, crawl_time), 1)
        except Exception:
            pass

    row = {
        "video_id":                 video_id,
        "crawl_time":               crawl_time,
        "time_since_publish_minutes": time_since,
        "view_count":               view_count,
        "like_count":               like_count,
        "comment_count":            comment_count,
        "subscriber_count":         subscriber_count,
        "video_status":             video_status,
    }

    csv_path = data_dir / "raw" / "timeseries" / "by_video" / f"{video_id}.csv"
    append_csv_row(csv_path, row, _TS_FIELDS)
    logger.debug("fetch_timeseries %s: views=%s status=%s", video_id, view_count, video_status)
    return row


# ── parsing helpers ────────────────────────────────────────────────────────

def _get_primary_info(init_data: dict) -> dict:
    contents = dig(init_data, "contents", "twoColumnWatchNextResults",
                   "results", "results", "contents") or []
    for item in contents:
        if "videoPrimaryInfoRenderer" in item:
            return item["videoPrimaryInfoRenderer"]
    return {}


def _get_secondary_info(init_data: dict) -> dict:
    contents = dig(init_data, "contents", "twoColumnWatchNextResults",
                   "results", "results", "contents") or []
    for item in contents:
        if "videoSecondaryInfoRenderer" in item:
            return item["videoSecondaryInfoRenderer"]
    return {}


def _parse_like_count(init_data: dict) -> int | None:
    try:
        primary = _get_primary_info(init_data)
        buttons = dig(primary, "videoActions", "menuRenderer", "topLevelButtons") or []
        for btn in buttons:
            # newer layout
            title = dig(btn, "segmentedLikeDislikeButtonViewModel",
                        "likeButtonViewModel", "likeButtonViewModel",
                        "toggleButtonViewModel", "toggleButtonViewModel",
                        "defaultButtonViewModel", "buttonViewModel", "title")
            if title:
                return parse_count_text(title)
            # older toggleButtonRenderer
            import re
            label = dig(btn, "toggleButtonRenderer", "defaultText",
                        "accessibility", "accessibilityData", "label") or ""
            if "like" in label.lower():
                m = re.search(r"[\d,\.]+[KMB千萬億]?", label)
                if m:
                    return parse_count_text(m.group())
    except Exception:
        pass
    return None


def _parse_comment_count(init_data: dict) -> int | None:
    try:
        for panel in init_data.get("engagementPanels") or []:
            text = dig(panel, "engagementPanelSectionListRenderer", "header",
                       "engagementPanelTitleHeaderRenderer", "contextualInfo",
                       "runs", 0, "text")
            if text:
                return parse_count_text(text)
        contents = dig(init_data, "contents", "twoColumnWatchNextResults",
                       "results", "results", "contents") or []
        for item in contents:
            r = dig(item, "itemSectionRenderer", "contents", 0,
                    "commentsEntryPointHeaderRenderer")
            if r:
                text = dig(r, "commentCount", "simpleText")
                if text:
                    return parse_count_text(text)
    except Exception:
        pass
    return None


def _parse_subscriber_count(init_data: dict) -> int | None:
    try:
        secondary = _get_secondary_info(init_data)
        sub_text = dig(secondary, "owner", "videoOwnerRenderer",
                       "subscriberCountText", "simpleText")
        if not sub_text:
            return None
        # Extract leading number + optional unit from text like "609萬位訂閱者" or "1.2M subscribers"
        m = re.search(r"([\d,\.]+\s*[千萬億KkMmBb]?)", sub_text)
        if m:
            return parse_count_text(m.group(1).strip())
    except Exception:
        pass
    return None
