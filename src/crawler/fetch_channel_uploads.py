"""
爬取追蹤頻道最新上傳的影片。
來源：GET /channel/{id}/videos → ytInitialData
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
    resp = client.get(
        f"https://www.youtube.com/channel/{channel_id}/videos",
        params={"hl": "zh-TW"},
    )
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_channel_uploads %s: GET failed (status=%s)", channel_id,
                       resp.status_code if resp else "None")
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        logger.warning("fetch_channel_uploads %s: ytInitialData not found", channel_id)
        return []

    results = _parse_uploads(data, channel_id)
    logger.info("fetch_channel_uploads %s: %d videos found", channel_id, len(results))
    return results[:max_results]


def _parse_uploads(data: dict, channel_id: str) -> list[dict]:
    results = []

    # videos tab → richGridRenderer or gridRenderer
    tabs = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs") or []
    for tab in tabs:
        tab_title = dig(tab, "tabRenderer", "title") or ""
        if tab_title not in ("Videos", "影片", "動画", "동영상"):
            continue
        content = dig(tab, "tabRenderer", "content") or {}

        # richGridRenderer (newer layout)
        rich_items = dig(content, "richGridRenderer", "contents") or []
        for item in rich_items:
            vr = dig(item, "richItemRenderer", "content", "videoRenderer")
            if vr:
                v = _parse_video_renderer(vr, channel_id)
                if v:
                    results.append(v)

        # sectionListRenderer → gridRenderer (older layout)
        sections = dig(content, "sectionListRenderer", "contents") or []
        for section in sections:
            items = dig(section, "itemSectionRenderer", "contents", 0,
                        "gridRenderer", "items") or []
            for item in items:
                vr = item.get("gridVideoRenderer") or item.get("videoRenderer")
                if vr:
                    v = _parse_video_renderer(vr, channel_id)
                    if v:
                        results.append(v)

    return results


def _parse_video_renderer(renderer: dict, channel_id: str) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    title = dig(renderer, "title", "runs", 0, "text") or dig(renderer, "title", "simpleText") or ""
    published_text = dig(renderer, "publishedTimeText", "simpleText") or ""
    view_text = dig(renderer, "viewCountText", "simpleText") or ""
    return {
        "video_id":            video_id,
        "title":               title,
        "channel_id":          channel_id,
        "published_time_text": published_text,
        "view_count_text":     view_text,
    }
