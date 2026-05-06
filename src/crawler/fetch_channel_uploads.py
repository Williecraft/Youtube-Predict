"""
爬取追蹤頻道最新上傳的影片。
來源：GET /feeds/videos.xml?channel_id={id}  (YouTube Atom RSS)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.utils.http_client import YouTubeClient

logger = logging.getLogger(__name__)

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt":   "http://www.youtube.com/xml/schemas/2015",
    "media":"http://search.yahoo.com/mrss/",
}
_RSS_URL = "https://www.youtube.com/feeds/videos.xml"


def fetch_channel_uploads(
    client: YouTubeClient,
    channel_id: str,
    max_results: int = 15,
) -> list[dict]:
    resp = client.get(_RSS_URL, params={"channel_id": channel_id})
    if resp is None or resp.status_code != 200:
        logger.warning("fetch_channel_uploads %s: GET failed (status=%s)", channel_id,
                       resp.status_code if resp else "None")
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        logger.warning("fetch_channel_uploads %s: XML parse error: %s", channel_id, exc)
        return []

    results = []
    for entry in root.findall("atom:entry", _NS)[:max_results]:
        video_id = _text(entry, "yt:videoId")
        if not video_id:
            continue
        results.append({
            "video_id":            video_id,
            "title":               _text(entry, "atom:title") or "",
            "channel_id":          channel_id,
            "published_time_text": _text(entry, "atom:published") or "",
            "view_count_text":     "",
        })

    logger.info("fetch_channel_uploads %s: %d videos found", channel_id, len(results))
    return results


def _text(element, tag: str) -> str | None:
    child = element.find(tag, _NS)
    return child.text if child is not None else None
