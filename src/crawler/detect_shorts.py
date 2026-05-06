"""
判定影片是否為 Shorts。
GET https://www.youtube.com/shorts/{video_id}，不跟隨 redirect：
  200 → Shorts
  303 → 長影片
  其他 → unknown（稍後重試）
"""

from __future__ import annotations

import logging

from src.utils.http_client import YouTubeClient

logger = logging.getLogger(__name__)

_SHORTS_URL = "https://www.youtube.com/shorts/{}"


def detect_shorts(client: YouTubeClient, video_id: str) -> tuple[str, int | None]:
    """
    Returns (result, status_code).
    result ∈ {"shorts", "long", "unknown"}
    """
    url = _SHORTS_URL.format(video_id)
    code = client.get_no_redirect(url)

    if code is None:
        logger.warning("detect_shorts %s: no response", video_id)
        return "unknown", None
    if code == 200:
        return "shorts", code
    if code in (301, 302, 303, 307, 308):
        return "long", code
    logger.warning("detect_shorts %s: unexpected status %d", video_id, code)
    return "unknown", code
