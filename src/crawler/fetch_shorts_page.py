"""
收集 YouTube Shorts 影片 ID。

使用「上傳時間排序」filter（SP_LAST_HOUR_SORT_NEW）搜尋 #shorts 相關關鍵字，
找到真正剛上傳的 Shorts 候選，再交由 fetch_static 的 HTTP redirect 確認 is_shorts。
注意：舊方法 (sp=EgQQARgD, 4 分鐘以下) 回傳的幾乎全是一般短影片而非 Shorts，
改用上傳時間排序後 yield 率大幅提升。
"""

from __future__ import annotations

import logging
import random

from src.crawler.fetch_search import SP_LAST_HOUR_SORT_NEW
from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

_SHORTS_KEYWORDS = [
    "#shorts",
    "#ytshorts",
    "#短片",
    "#shortsvideo",
    "#shorts 台灣",
    "#shorts 日本",
    "#shorts 搞笑",
    "#shorts 遊戲",
    "#shorts 美食",
    "#shorts 音樂",
    "#shorts ASMR",
    "#shorts vlog",
    "#shorts 教學",
    "#shorts 動漫",
    "youtube shorts",
]


def fetch_shorts_page(
    client: YouTubeClient,
    max_results: int = 20,
) -> list[dict]:
    """
    Collect recently-uploaded Shorts candidates via upload-date-sorted search.
    Actual is_shorts confirmation is done by fetch_static's redirect check.
    """
    seen: dict[str, dict] = {}
    keywords = random.sample(_SHORTS_KEYWORDS, k=min(len(_SHORTS_KEYWORDS), 6))

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

    logger.info("fetch_shorts_page: %d candidates collected", len(result))
    return result


def _search_shorts(client: YouTubeClient, keyword: str) -> list[dict]:
    resp = client.get(
        "https://www.youtube.com/results",
        params={"search_query": keyword, "sp": SP_LAST_HOUR_SORT_NEW, "hl": "zh-TW"},
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
