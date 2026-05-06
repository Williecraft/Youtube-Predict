"""
爬取影片留言的單一時間點 snapshot。
每次呼叫對應一個 snapshot_label ∈ {"t1h", "t2h", "t3h"}。
最多抓 max_comments 則熱門留言（YouTube 預設 "Top comments" 排序）。

輸出：data/raw/comments/by_video/{video_id}_{snapshot_label}.jsonl
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.utils.http_client import YouTubeClient, dig
from src.utils.io import append_jsonl
from src.utils.time import format_iso, now_utc

logger = logging.getLogger(__name__)

_MAX_PAGES = 4  # safety cap; 50 comments/page → up to 200 comments


def fetch_comments_snapshot(
    client: YouTubeClient,
    video_id: str,
    snapshot_label: str,
    data_dir: Path,
    max_comments: int = 200,
) -> int:
    """
    Fetch top comments and write to JSONL.
    Returns number of comments saved.
    """
    out_path = data_dir / "raw" / "comments" / "by_video" / f"{video_id}_{snapshot_label}.jsonl"
    crawl_time = format_iso(now_utc())

    comments = _fetch_all_comments(client, video_id, max_comments)

    for c in comments:
        c["snapshot_label"] = snapshot_label
        c["crawl_time"] = crawl_time
        append_jsonl(out_path, c)

    logger.info("fetch_comments %s [%s]: %d comments saved", video_id, snapshot_label, len(comments))
    return len(comments)


def _fetch_all_comments(client: YouTubeClient, video_id: str, max_comments: int) -> list[dict]:
    """Paginate through comments using continuation tokens."""
    comments: list[dict] = []

    # First call: next endpoint to get initial comment token
    data = client.post_innertube("next", {"videoId": video_id})
    if not data:
        logger.warning("fetch_comments %s: next endpoint failed", video_id)
        return []

    continuation_token = _find_comments_continuation(data)
    if not continuation_token:
        logger.warning("fetch_comments %s: no comments continuation found", video_id)
        return []

    page = 0
    while continuation_token and len(comments) < max_comments and page < _MAX_PAGES:
        client.jitter_sleep(1.0, 2.5)
        page_data = client.post_innertube(
            "next",
            {"continuation": continuation_token},
        )
        if not page_data:
            break

        new_comments, continuation_token = _parse_comment_page(page_data)
        comments.extend(new_comments)
        page += 1

    return comments[:max_comments]


def _find_comments_continuation(data: dict) -> str | None:
    """Find the initial continuation token for comments from the next endpoint response."""
    # Check engagementPanels for comment section
    for panel in data.get("engagementPanels") or []:
        token = dig(
            panel,
            "engagementPanelSectionListRenderer", "content",
            "sectionListRenderer", "contents", 0,
            "itemSectionRenderer", "contents", 0,
            "continuationItemRenderer", "continuationEndpoint",
            "continuationCommand", "token",
        )
        if token:
            return token

    # Also check in the main contents
    contents = dig(data, "contents", "twoColumnWatchNextResults",
                   "results", "results", "contents") or []
    for item in contents:
        for sub in dig(item, "itemSectionRenderer", "contents") or []:
            token = dig(sub, "continuationItemRenderer", "continuationEndpoint",
                        "continuationCommand", "token")
            if token:
                return token
    return None


def _parse_comment_page(data: dict) -> tuple[list[dict], str | None]:
    """Parse one page of comments. Returns (comments, next_continuation_token)."""
    comments = []
    next_token = None

    # comment pages come back in onResponseReceivedEndpoints
    endpoints = data.get("onResponseReceivedEndpoints") or []
    for ep in endpoints:
        # appendContinuationItemsAction or reloadContinuationItemsCommand
        for action_key in ("appendContinuationItemsAction", "reloadContinuationItemsCommand"):
            action = ep.get(action_key, {})
            items = action.get("continuationItems") or []
            for item in items:
                # commentThreadRenderer
                ctr = item.get("commentThreadRenderer")
                if ctr:
                    comment = _parse_comment_thread(ctr)
                    if comment:
                        comments.append(comment)
                # continuationItemRenderer → next page token
                cir = item.get("continuationItemRenderer")
                if cir:
                    token = dig(cir, "continuationEndpoint", "continuationCommand", "token")
                    if token:
                        next_token = token

    return comments, next_token


def _parse_comment_thread(renderer: dict) -> dict | None:
    comment = dig(renderer, "comment", "commentRenderer")
    if not comment:
        return None

    comment_id = comment.get("commentId")
    if not comment_id:
        return None

    text_runs = dig(comment, "contentText", "runs") or []
    text = "".join(r.get("text", "") for r in text_runs)
    like_count_text = dig(comment, "voteCount", "simpleText") or "0"
    published_at = dig(comment, "publishedTimeText", "runs", 0, "text") or ""

    try:
        like_count = int(like_count_text.replace(",", ""))
    except (ValueError, AttributeError):
        like_count = 0

    return {
        "comment_id": comment_id,
        "comment_text": text,
        "comment_like_count": like_count,
        "comment_published_at": published_at,
    }
