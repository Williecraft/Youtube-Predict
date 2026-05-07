"""
爬取 YouTube 探索（Explore）分類頁的熱門影片。

各分類直接 GET 對應 URL → ytInitialData，無需登入。
支援區域參數 gl=TW/JP/US/KR（對 news/sports 等有效）。

有效分類（以 gl=TW 驗證）：
  gaming   /gaming
  news     /news
  sports   /sports
  live     /live
  podcasts /podcasts
  movies   /movies
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

_REGIONS = ["TW", "JP", "US", "KR"]

# (category_label, URL)
_EXPLORE_PAGES: list[tuple[str, str]] = [
    ("gaming",   "https://www.youtube.com/gaming"),
    ("news",     "https://www.youtube.com/news"),
    ("sports",   "https://www.youtube.com/sports"),
    ("live",     "https://www.youtube.com/live"),
    ("podcasts", "https://www.youtube.com/podcasts"),
    ("movies",   "https://www.youtube.com/movies"),
]


def fetch_explore(
    client: YouTubeClient,
    regions: list[str] = _REGIONS,
) -> list[dict]:
    """
    Scrape all explore category pages for each region.
    Returns deduplicated list of video dicts.
    """
    seen: dict[str, dict] = {}
    for region in regions:
        for category, url in _EXPLORE_PAGES:
            videos = _fetch_category(client, url, category, region)
            for v in videos:
                vid = v["video_id"]
                if vid not in seen:
                    seen[vid] = v
            logger.info("fetch_explore %s/%s: %d videos (unique so far: %d)",
                        region, category, len(videos), len(seen))
        client.jitter_sleep(1.5, 3.0)
    return list(seen.values())


def _fetch_category(client: YouTubeClient, url: str, category: str, region: str) -> list[dict]:
    resp = client.get(url, params={"gl": region, "hl": "zh-TW"})
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_explore %s/%s: GET failed (status=%s)",
                       region, category, resp.status_code if resp else "None")
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        logger.warning("fetch_explore %s/%s: ytInitialData not found", region, category)
        return []

    results = []
    seen: set[str] = set()
    for renderer in _find_video_renderers(data):
        v = _parse_video_renderer(renderer, region, category)
        if v and v["video_id"] not in seen:
            seen.add(v["video_id"])
            results.append(v)
    return results


def _find_video_renderers(obj, _depth=0):
    """Recursively find all videoRenderer dicts regardless of page layout."""
    if _depth > 25 or not isinstance(obj, (dict, list)):
        return
    if isinstance(obj, dict):
        if "videoId" in obj and "title" in obj:
            yield obj
            return
        for v in obj.values():
            yield from _find_video_renderers(v, _depth + 1)
    else:
        for item in obj:
            yield from _find_video_renderers(item, _depth + 1)


def _parse_video_renderer(renderer: dict, region: str, category: str) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    return {
        "video_id":            video_id,
        "title":               dig(renderer, "title", "runs", 0, "text") or dig(renderer, "title", "simpleText") or "",
        "channel_id":          dig(renderer, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId") or "",
        "channel_title":       dig(renderer, "ownerText", "runs", 0, "text") or "",
        "region":              region,
        "category":            category,
        "view_count_text":     dig(renderer, "viewCountText", "simpleText") or "",
        "published_time_text": dig(renderer, "publishedTimeText", "simpleText") or "",
    }
