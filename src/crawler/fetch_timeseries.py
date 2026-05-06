"""
爬取一支影片的當前時序快照（view / like / comment count + subscriber + status）。
每次呼叫對應 timeseries CSV 的一筆新 row。

來源：
  1. InnerTube player endpoint  → view_count (精確), video_status
  2. watch page ytInitialData   → like_count, comment_count, subscriber_count (近似)
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.utils.http_client import YouTubeClient, dig, parse_count_text
from src.utils.io import append_csv_row
from src.utils.time import format_iso, now_utc, minutes_between

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
    """
    Fetch one timeseries row for video_id, append to CSV, and return the row dict.
    Returns None if the fetch failed entirely.
    """
    crawl_time = format_iso(now_utc())

    # ── 1. player endpoint (exact view count + status) ────────────────────
    player = client.post_innertube("player", {"videoId": video_id})
    if not player:
        logger.warning("fetch_timeseries %s: player endpoint failed", video_id)
        return None

    video_details = player.get("videoDetails", {})
    playability = player.get("playabilityStatus", {})

    view_count_raw = video_details.get("viewCount")
    view_count = int(view_count_raw) if view_count_raw and str(view_count_raw).isdigit() else None
    video_status = playability.get("status", "UNKNOWN")

    # ── 2. watch page for engagement counts ───────────────────────────────
    client.jitter_sleep(0.8, 2.0)
    init_data, _ = client.get_watch_page(video_id)

    like_count = _parse_like_count(init_data)
    comment_count = _parse_comment_count(init_data)
    subscriber_count = _parse_subscriber_count(init_data)

    # ── assemble row ──────────────────────────────────────────────────────
    time_since = None
    if publish_time:
        try:
            time_since = round(minutes_between(publish_time, crawl_time), 1)
        except Exception:
            pass

    row = {
        "video_id": video_id,
        "crawl_time": crawl_time,
        "time_since_publish_minutes": time_since,
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "subscriber_count": subscriber_count,
        "video_status": video_status,
    }

    # ── persist ───────────────────────────────────────────────────────────
    csv_path = data_dir / "raw" / "timeseries" / "by_video" / f"{video_id}.csv"
    append_csv_row(csv_path, row, _TS_FIELDS)
    logger.debug("fetch_timeseries %s: views=%s status=%s", video_id, view_count, video_status)

    return row


# ── parsing helpers ────────────────────────────────────────────────────────

def _parse_like_count(init_data: dict) -> int | None:
    """
    Like count lives in the primary info renderer's like button.
    YouTube shows approximate text (e.g. "1.2K") — we parse best-effort.
    """
    # segmentedLikeDislikeButtonViewModel path (newer layout)
    try:
        primary = _get_primary_info(init_data)
        buttons = dig(primary, "videoActions", "menuRenderer", "topLevelButtons") or []
        for btn in buttons:
            # likeButtonViewModel path
            lbvm = dig(btn, "segmentedLikeDislikeButtonViewModel",
                       "likeButtonViewModel", "likeButtonViewModel",
                       "toggleButtonViewModel", "toggleButtonViewModel",
                       "defaultButtonViewModel", "buttonViewModel", "title")
            if lbvm:
                return parse_count_text(lbvm)
            # older toggleButtonRenderer
            text = dig(btn, "toggleButtonRenderer", "defaultText", "accessibility",
                       "accessibilityData", "label")
            if text and "like" in text.lower():
                import re
                m = re.search(r"[\d,\.]+[KMB千萬億]?", text)
                if m:
                    return parse_count_text(m.group())
    except Exception:
        pass
    return None


def _parse_comment_count(init_data: dict) -> int | None:
    try:
        # commentsEntryPointHeaderRenderer
        engagement_panels = init_data.get("engagementPanels") or []
        for panel in engagement_panels:
            count_text = dig(
                panel,
                "engagementPanelSectionListRenderer", "header",
                "engagementPanelTitleHeaderRenderer", "contextualInfo", "runs", 0, "text",
            )
            if count_text:
                return parse_count_text(count_text)

        # fallback: commentsEntryPointHeaderRenderer in main contents
        contents = dig(init_data, "contents", "twoColumnWatchNextResults",
                       "results", "results", "contents") or []
        for item in contents:
            renderer = dig(item, "itemSectionRenderer", "contents", 0,
                           "commentsEntryPointHeaderRenderer")
            if renderer:
                text = dig(renderer, "commentCount", "simpleText")
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
        return parse_count_text(sub_text)
    except Exception:
        return None


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
