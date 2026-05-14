"""
收集 YouTube Shorts 影片 ID。

YouTube /shorts 首頁一次只顯示單支影片，InnerTube FEshorts 返回 400。
實際做法：搜尋 "#shorts" hashtag 並加上 sp=EgQQARgD（短片 ≤4 分鐘過濾器），
多個廣泛關鍵字輪流搜尋以增加多樣性。
"""

from __future__ import annotations

import logging
import random

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

# YouTube search "under 4 minutes" filter  (protobuf-encoded sp parameter)
_SP_SHORT = "EgQQARgD"

_BROAD_KEYWORDS = [
    "#shorts",
    "#shorts 台灣",
    "#shorts 遊戲",
    "#shorts 美食",
    "#shorts 音樂",
    "#shorts 搞笑",
    "#shorts 生活",
    "#shorts 動漫",
]


def fetch_shorts_page(
    client: YouTubeClient,
    max_results: int = 10,
) -> list[dict]:
    """
    Collect Shorts video IDs via YouTube search with short-video filter.
    max_results: total unique Shorts to return; 0 = no cap.
    """
    seen: dict[str, dict] = {}
    keywords = random.sample(_BROAD_KEYWORDS, k=min(len(_BROAD_KEYWORDS), 3))

    for kw in keywords:
        if max_results and len(seen) >= max_results:
            break
        videos = _search_shorts(client, kw)
        for v in videos:
            vid = v["video_id"]
            if vid not in seen:
                seen[vid] = v

    result = list(seen.values())
    if max_results and len(result) > max_results:
        result = random.sample(result, max_results)

    logger.info("fetch_shorts_page: %d Shorts collected", len(result))
    return result


def _search_shorts(client: YouTubeClient, keyword: str) -> list[dict]:
    resp = client.get(
        "https://www.youtube.com/results",
        params={"search_query": keyword, "sp": _SP_SHORT, "hl": "zh-TW"},
    )
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_shorts_page search '%s': HTTP %s", keyword,
                       resp.status_code if resp else "None")
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        logger.warning("fetch_shorts_page search '%s': ytInitialData not found", keyword)
        return []

    results = []
    contents = (
        dig(data, "contents", "twoColumnSearchResultsRenderer", "primaryContents",
            "sectionListRenderer", "contents") or []
    )
    for section in contents:
        items = dig(section, "itemSectionRenderer", "contents") or []
        for item in items:
            vr = item.get("videoRenderer") or item.get("reelItemRenderer")
            if not vr:
                continue
            video_id = vr.get("videoId")
            if not video_id:
                continue
            title = (
                dig(vr, "title", "runs", 0, "text")
                or dig(vr, "title", "simpleText")
                or dig(vr, "headline", "simpleText")
                or ""
            )
            channel_id = (
                dig(vr, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId")
                or dig(vr, "navigationEndpoint", "browseEndpoint", "browseId")
                or ""
            )
            channel_title = dig(vr, "ownerText", "runs", 0, "text") or ""
            results.append({
                "video_id":      video_id,
                "title":         title,
                "channel_id":    channel_id,
                "channel_title": channel_title,
            })

    logger.info("fetch_shorts_page search '%s': %d results", keyword, len(results))
    return results
