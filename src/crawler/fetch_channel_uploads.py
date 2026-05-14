"""
爬取追蹤頻道最新上傳的影片。
來源：InnerTube POST /browse（browseId=channelId, params=Videos tab）
YouTube Atom RSS (/feeds/videos.xml) 已在 2026 年停用（返回 404）。
YouTube 頻道頁 HTML 使用 lockupViewModel 格式（不含 videoId），故改用 InnerTube。
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient, dig

logger = logging.getLogger(__name__)

# Base64-encoded protobuf for the "Videos" tab on a channel page
_VIDEOS_TAB_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"


def fetch_channel_uploads(
    client: YouTubeClient,
    channel_id: str,
    max_results: int = 15,
) -> list[dict]:
    data = client.post_innertube(
        "browse",
        {"browseId": channel_id, "params": _VIDEOS_TAB_PARAMS},
    )
    if not data:
        logger.warning("fetch_channel_uploads %s: InnerTube browse returned None", channel_id)
        return []

    results = _parse_videos_tab(data, channel_id, max_results)
    logger.info("fetch_channel_uploads %s: %d videos found", channel_id, len(results))
    return results


def _parse_videos_tab(data: dict, channel_id: str, max_results: int) -> list[dict]:
    tabs = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs") or []
    for tab in tabs:
        tab_r = tab.get("tabRenderer", {})
        if not tab_r.get("selected"):
            continue
        items = dig(tab_r, "content", "richGridRenderer", "contents") or []
        results = []
        for item in items:
            vr = dig(item, "richItemRenderer", "content", "videoRenderer")
            if not vr:
                continue
            video_id = vr.get("videoId")
            if not video_id:
                continue
            results.append({
                "video_id":            video_id,
                "title":               dig(vr, "title", "runs", 0, "text") or dig(vr, "title", "simpleText") or "",
                "channel_id":          channel_id,
                "published_time_text": dig(vr, "publishedTimeText", "simpleText") or "",
                "view_count_text":     dig(vr, "viewCountText", "simpleText") or "",
            })
            if len(results) >= max_results:
                break
        return results
    return []
