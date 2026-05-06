"""
用關鍵字搜尋 YouTube，回傳最多 max_results 部影片的基本資訊。
使用 InnerTube search endpoint；失敗時 fallback 到 results 頁 HTML。
"""

from __future__ import annotations

import logging
import random

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)


def fetch_search(
    client: YouTubeClient,
    keyword: str,
    max_results: int = 10,
) -> list[dict]:
    """
    Returns up to max_results dicts with:
      video_id, title, channel_id, channel_title, view_count_text, published_time_text
    """
    data = client.post_innertube("search", {"query": keyword})

    if data is None:
        resp = client.get(
            "https://www.youtube.com/results",
            params={"search_query": keyword, "hl": "zh-TW"},
        )
        if resp and resp.status_code == 200:
            data = extract_js_var(resp.text, "ytInitialData")

    if not data:
        logger.warning("fetch_search '%s': no data", keyword)
        return []

    results = _parse_search(data)
    if len(results) > max_results:
        results = random.sample(results, max_results)

    logger.info("fetch_search '%s': %d results (returning %d)", keyword, len(results), len(results))
    return results


def _parse_search(data: dict) -> list[dict]:
    results = []

    # InnerTube search response path
    contents = (
        dig(data, "contents", "twoColumnSearchResultsRenderer", "primaryContents",
            "sectionListRenderer", "contents")
        or []
    )
    for section in contents:
        items = dig(section, "itemSectionRenderer", "contents") or []
        for item in items:
            vr = item.get("videoRenderer")
            if vr:
                parsed = _parse_video_renderer(vr)
                if parsed:
                    results.append(parsed)

    return results


def _parse_video_renderer(renderer: dict) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None

    title = dig(renderer, "title", "runs", 0, "text") or dig(renderer, "title", "simpleText") or ""
    channel_id = dig(renderer, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId") or ""
    channel_title = dig(renderer, "ownerText", "runs", 0, "text") or ""
    view_text = dig(renderer, "viewCountText", "simpleText") or ""
    published_text = dig(renderer, "publishedTimeText", "simpleText") or ""

    return {
        "video_id": video_id,
        "title": title,
        "channel_id": channel_id,
        "channel_title": channel_title,
        "view_count_text": view_text,
        "published_time_text": published_text,
    }
