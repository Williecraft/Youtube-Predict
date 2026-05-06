"""
爬取追蹤頻道最新上傳的影片。
使用 InnerTube browse endpoint，browseId 為頻道的 uploads playlist（UC... → UU...）。
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)


def fetch_channel_uploads(
    client: YouTubeClient,
    channel_id: str,
    max_results: int = 3,
) -> list[dict]:
    """
    Returns up to max_results recently uploaded video dicts:
      video_id, title, channel_id, published_time_text, view_count_text
    Sorted by upload recency (newest first, as returned by YouTube).
    """
    # UC{rest} → UU{rest}
    playlist_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id

    data = client.post_innertube(
        "browse",
        {"browseId": playlist_id},
        params={"hl": "zh-TW"},
    )

    if data is None:
        # fallback: channel /videos page
        resp = client.get(
            f"https://www.youtube.com/channel/{channel_id}/videos",
            params={"hl": "zh-TW"},
        )
        if resp and resp.status_code == 200:
            data = extract_js_var(resp.text, "ytInitialData")

    if not data:
        logger.warning("fetch_channel_uploads %s: no data", channel_id)
        return []

    results = _parse_uploads(data, channel_id)
    logger.info("fetch_channel_uploads %s: %d videos found", channel_id, len(results))
    return results[:max_results]


def _parse_uploads(data: dict, channel_id: str) -> list[dict]:
    results = []

    # playlist browse response
    items = (
        dig(data, "contents", "singleColumnBrowseResultsRenderer", "tabs", 0,
            "tabRenderer", "content", "sectionListRenderer", "contents", 0,
            "itemSectionRenderer", "contents", 0, "playlistVideoListRenderer", "contents")
        or dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs", 0,
               "tabRenderer", "content", "sectionListRenderer", "contents", 0,
               "itemSectionRenderer", "contents", 0, "shelfRenderer", "content",
               "horizontalListRenderer", "items")
        or []
    )

    for item in items:
        vr = item.get("playlistVideoRenderer") or item.get("videoRenderer")
        if not vr:
            continue
        video_id = vr.get("videoId")
        if not video_id:
            continue
        title = dig(vr, "title", "runs", 0, "text") or dig(vr, "title", "simpleText") or ""
        published_text = dig(vr, "publishedTimeText", "simpleText") or ""
        view_text = dig(vr, "viewCountText", "simpleText") or ""
        results.append({
            "video_id": video_id,
            "title": title,
            "channel_id": channel_id,
            "published_time_text": published_text,
            "view_count_text": view_text,
        })

    return results
