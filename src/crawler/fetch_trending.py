"""
爬取多區發燒影片清單。
來源：GET /feed/trending?gl={region} → ytInitialData
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

_REGIONS = ["TW", "JP", "US", "KR"]


def fetch_trending(
    client: YouTubeClient,
    regions: list[str] = _REGIONS,
) -> list[dict]:
    seen: dict[str, dict] = {}
    for region in regions:
        videos = _fetch_region(client, region)
        for v in videos:
            vid = v.get("video_id")
            if vid and vid not in seen:
                seen[vid] = v
        logger.info("fetch_trending %s: %d videos (unique so far: %d)", region, len(videos), len(seen))
        client.jitter_sleep(1.5, 3.0)
    return list(seen.values())


def _fetch_region(client: YouTubeClient, region: str) -> list[dict]:
    resp = client.get(
        "https://www.youtube.com/feed/trending",
        params={"gl": region, "hl": "zh-TW"},
    )
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_trending %s: GET failed (status=%s)", region,
                       resp.status_code if resp else "None")
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        logger.warning("fetch_trending %s: ytInitialData not found in page", region)
        return []

    return _parse_trending(data, region)


def _parse_trending(data: dict, region: str) -> list[dict]:
    results = []
    seen: set[str] = set()
    for renderer in _find_video_renderers(data):
        v = _parse_video_renderer(renderer, region)
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


def _parse_video_renderer(renderer: dict, region: str) -> dict | None:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    return {
        "video_id":            video_id,
        "title":               dig(renderer, "title", "runs", 0, "text") or dig(renderer, "title", "simpleText") or "",
        "channel_id":          dig(renderer, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId") or "",
        "channel_title":       dig(renderer, "ownerText", "runs", 0, "text") or "",
        "region":              region,
        "view_count_text":     dig(renderer, "viewCountText", "simpleText") or "",
        "published_time_text": dig(renderer, "publishedTimeText", "simpleText") or "",
    }
