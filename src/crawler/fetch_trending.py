"""
爬取多區發燒影片清單。
使用 InnerTube browse endpoint（browseId=FEtrending），多區合併後去重。
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

_REGIONS = ["TW", "JP", "US", "KR"]
_TRENDING_BROWSE_ID = "FEtrending"


def fetch_trending(
    client: YouTubeClient,
    regions: list[str] = _REGIONS,
) -> list[dict]:
    """
    Returns a list of dicts with keys: video_id, title, channel_id, channel_title,
    region (first seen), view_count_text, published_time_text.
    De-duped by video_id across regions.
    """
    seen: dict[str, dict] = {}

    for region in regions:
        videos = _fetch_region(client, region)
        for v in videos:
            vid = v.get("video_id")
            if vid and vid not in seen:
                seen[vid] = v
        logger.info("fetch_trending %s: %d videos (total unique so far: %d)", region, len(videos), len(seen))
        client.jitter_sleep(1.5, 3.0)

    return list(seen.values())


def _fetch_region(client: YouTubeClient, region: str) -> list[dict]:
    data = client.post_innertube(
        "browse",
        {"browseId": _TRENDING_BROWSE_ID},
        params={"gl": region, "hl": "zh-TW"},
    )
    if data is None:
        # fallback: GET the trending page and parse ytInitialData
        resp = client.get(
            "https://www.youtube.com/feed/trending",
            params={"gl": region, "hl": "zh-TW"},
        )
        if resp and resp.status_code == 200:
            data = extract_js_var(resp.text, "ytInitialData")

    if not data:
        logger.warning("fetch_trending %s: no data", region)
        return []

    return _parse_trending(data, region)


def _parse_trending(data: dict, region: str) -> list[dict]:
    results: list[dict] = []

    # InnerTube trending structure: contents → twoColumnBrowseResultsRenderer → tabs[0] → ...
    tabs = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs")
    if not tabs:
        # Some responses wrap differently
        tabs = dig(data, "header", "feedTabbedHeaderRenderer")

    sections = _collect_sections(data)
    for section in sections:
        for renderer in _iter_video_renderers(section):
            v = _parse_video_renderer(renderer, region)
            if v:
                results.append(v)

    return results


def _collect_sections(data: dict) -> list[dict]:
    """Walk the browse response and collect all sectionListRenderer.contents items."""
    sections = []
    tabs = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs") or []
    for tab in tabs:
        content = dig(tab, "tabRenderer", "content") or {}
        sl = content.get("sectionListRenderer") or {}
        for item in sl.get("contents", []):
            sections.append(item)
    # richGridRenderer path (newer layout)
    rich = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs", 0,
               "tabRenderer", "content", "richGridRenderer", "contents") or []
    sections.extend(rich)
    return sections


def _iter_video_renderers(section: dict):
    """Yield videoRenderer dicts from various nesting levels."""
    for key in ("itemSectionRenderer", "shelfRenderer", "richItemRenderer"):
        inner = section.get(key, {})
        if not inner:
            continue
        # richItemRenderer → content → videoRenderer
        if "content" in inner:
            vr = inner["content"].get("videoRenderer")
            if vr:
                yield vr
        # itemSectionRenderer → contents → shelfRenderer → ...
        for item in inner.get("contents", []):
            shelf = item.get("shelfRenderer", {})
            expanded = shelf.get("content", {}).get("expandedShelfContentsRenderer", {})
            for shelf_item in expanded.get("items", []):
                vr = shelf_item.get("videoRenderer")
                if vr:
                    yield vr
            vr = item.get("videoRenderer")
            if vr:
                yield vr


def _parse_video_renderer(renderer: dict, region: str) -> dict | None:
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
        "region": region,
        "view_count_text": view_text,
        "published_time_text": published_text,
    }
