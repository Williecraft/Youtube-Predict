"""
用關鍵字搜尋 YouTube。
來源：GET /results?search_query={keyword} → ytInitialData
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
    resp = client.get(
        "https://www.youtube.com/results",
        params={"search_query": keyword, "hl": "zh-TW"},
    )
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_search '%s': GET failed (status=%s)", keyword,
                       resp.status_code if resp else "None")
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        logger.warning("fetch_search '%s': ytInitialData not found", keyword)
        return []

    results = _parse_search(data)
    if len(results) > max_results:
        results = random.sample(results, max_results)

    logger.info("fetch_search '%s': %d results (returning %d)", keyword, len(results), len(results))
    return results


def _parse_search(data: dict) -> list[dict]:
    results = []
    contents = (
        dig(data, "contents", "twoColumnSearchResultsRenderer", "primaryContents",
            "sectionListRenderer", "contents") or []
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
    return {
        "video_id":            video_id,
        "title":               dig(renderer, "title", "runs", 0, "text") or "",
        "channel_id":          dig(renderer, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId") or "",
        "channel_title":       dig(renderer, "ownerText", "runs", 0, "text") or "",
        "view_count_text":     dig(renderer, "viewCountText", "simpleText") or "",
        "published_time_text": dig(renderer, "publishedTimeText", "simpleText") or "",
    }
