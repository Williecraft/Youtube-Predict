"""
收集 YouTube Shorts 候選影片 ID。

策略（按可靠度排序）：
  1. 已知 Shorts 頻道的 /shorts tab → 最可靠，幾乎全是真 Shorts
  2. GET youtube.com/shorts overlay → 目前正在播的 1 筆 Shorts
  3. 關鍵字搜尋（備用，命中率低）

實際 is_shorts 確認仍由 collect_from_shorts 的 HTTP redirect pre-filter 完成。
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from src.crawler.fetch_search import SP_LAST_HOUR_SORT_NEW
from src.utils.http_client import YouTubeClient, dig, extract_js_var

logger = logging.getLogger(__name__)

_SHORTS_KEYWORDS = [
    "#shorts", "#ytshorts", "#短片", "#shortsvideo",
    "#shorts 台灣", "#shorts 日本", "#shorts 搞笑", "#shorts 遊戲",
]
_SHORTS_PER_CHANNEL = 2

# Cache of known Shorts channel IDs (populated from videos_static.json on first call)
_shorts_channel_cache: list[str] = []


def _load_shorts_channels() -> list[str]:
    """Load channel IDs that have confirmed Shorts from videos_static.json."""
    global _shorts_channel_cache
    if _shorts_channel_cache:
        return _shorts_channel_cache

    # Try to find videos_static.json relative to repo root
    import json
    from collections import Counter

    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "raw" / "static" / "videos_static.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            static = json.loads(path.read_text(encoding="utf-8"))
            channel_counts: Counter = Counter()
            for v in static.values():
                if v.get("is_shorts") and v.get("channel_id"):
                    channel_counts[v["channel_id"]] += 1
            # Keep channels with at least 1 confirmed Short; prefer prolific channels
            _shorts_channel_cache = [ch for ch, _ in channel_counts.most_common()]
            logger.info("Loaded %d Shorts channels from static", len(_shorts_channel_cache))
            return _shorts_channel_cache
        except Exception as exc:
            logger.warning("Failed to load Shorts channels: %s", exc)

    return []


def fetch_shorts_page(
    client: YouTubeClient,
    max_results: int = 160,
) -> list[dict]:
    """
    Return candidate video dicts (video_id, title, channel_id, channel_title).
    Actual Shorts confirmation done by caller via HTTP redirect check.
    """
    seen: dict[str, dict] = {}

    # ── Strategy 1: known Shorts channels' /shorts tab ───────────────────
    channels = _load_shorts_channels()
    # Sample a batch of channels each call (rotate through them)
    sample_channels = random.sample(channels, k=min(len(channels), 15)) if channels else []
    for ch_id in sample_channels:
        if len(seen) >= max_results:
            break
        for v in _fetch_channel_shorts_tab(client, ch_id)[:_SHORTS_PER_CHANNEL]:
            if v["video_id"] not in seen:
                seen[v["video_id"]] = v
        client.jitter_sleep(0.3, 0.7)

    # ── Strategy 2: GET /shorts overlay (1 video) ────────────────────────
    v = _fetch_from_shorts_overlay(client)
    if v and v["video_id"] not in seen:
        seen[v["video_id"]] = v

    # ── Strategy 3: keyword search fallback ──────────────────────────────
    if len(seen) < max_results // 2:
        keywords = random.sample(_SHORTS_KEYWORDS, k=min(len(_SHORTS_KEYWORDS), 4))
        for kw in keywords:
            if len(seen) >= max_results:
                break
            for v in _search_candidates(client, kw):
                if v["video_id"] not in seen:
                    seen[v["video_id"]] = v

    result = list(seen.values())
    if len(result) > max_results:
        result = result[:max_results]

    logger.info("fetch_shorts_page: %d candidates (%d channels sampled)",
                len(result), len(sample_channels))
    return result


# ── Channel /shorts tab ───────────────────────────────────────────────────────

def _fetch_channel_shorts_tab(client: YouTubeClient, channel_id: str) -> list[dict]:
    """Browse a channel's Shorts tab and extract reelItemRenderer items."""
    url = f"https://www.youtube.com/channel/{channel_id}/shorts"
    resp = client.get(url, params={"hl": "zh-TW"})
    if resp is None or resp.status_code != 200:
        return []

    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        return []

    results: list[dict] = []
    _extract_reel_items_recursive(data, results, depth=0)

    if results:
        logger.debug("channel %s /shorts: %d videos", channel_id, len(results))
    return results


def _extract_reel_items_recursive(node, results: list[dict], depth: int = 0) -> None:
    if depth > 15 or not node:
        return
    if isinstance(node, dict):
        # Old format: reelItemRenderer
        if "reelItemRenderer" in node:
            v = _parse_reel_item(node["reelItemRenderer"])
            if v:
                results.append(v)
            return
        # New format (2024+): richItemRenderer.content.shortsLockupViewModel
        if "shortsLockupViewModel" in node:
            v = _parse_shorts_lockup(node["shortsLockupViewModel"])
            if v:
                results.append(v)
            return
        # Also handle richItemRenderer wrapping either format
        if "richItemRenderer" in node:
            content = node["richItemRenderer"].get("content", {})
            if "reelItemRenderer" in content:
                v = _parse_reel_item(content["reelItemRenderer"])
                if v:
                    results.append(v)
            elif "shortsLockupViewModel" in content:
                v = _parse_shorts_lockup(content["shortsLockupViewModel"])
                if v:
                    results.append(v)
            return
        for val in node.values():
            _extract_reel_items_recursive(val, results, depth + 1)
    elif isinstance(node, list):
        for item in node:
            _extract_reel_items_recursive(item, results, depth + 1)


def _parse_shorts_lockup(vm: dict) -> dict | None:
    """Parse shortsLockupViewModel (new YouTube renderer format, 2024+)."""
    video_id = dig(vm, "onTap", "innertubeCommand", "reelWatchEndpoint", "videoId")
    if not video_id:
        # Fallback: entityId sometimes encodes the video ID
        entity_id = vm.get("entityId", "")
        if entity_id.startswith("shorts-shelf-item-"):
            video_id = entity_id.replace("shorts-shelf-item-", "")
    if not video_id:
        return None
    title = (
        dig(vm, "overlayMetadata", "primaryText", "content")
        or dig(vm, "accessibilityText")
        or ""
    )
    return {"video_id": video_id, "title": title, "channel_id": "", "channel_title": ""}


def _parse_reel_item(reel: dict) -> dict | None:
    video_id = reel.get("videoId")
    if not video_id:
        return None
    title = (
        dig(reel, "headline", "simpleText")
        or dig(reel, "headline", "runs", 0, "text")
        or dig(reel, "title", "simpleText")
        or dig(reel, "title", "runs", 0, "text")
        or ""
    )
    channel_id = (
        dig(reel, "navigationEndpoint", "browseEndpoint", "browseId")
        or dig(reel, "ownerText", "runs", 0, "navigationEndpoint", "browseEndpoint", "browseId")
        or ""
    )
    channel_title = dig(reel, "ownerText", "runs", 0, "text") or ""
    return {"video_id": video_id, "title": title, "channel_id": channel_id, "channel_title": channel_title}


# ── /shorts overlay ───────────────────────────────────────────────────────────

def _fetch_from_shorts_overlay(client: YouTubeClient) -> dict | None:
    resp = client.get("https://www.youtube.com/shorts", params={"hl": "zh-TW"})
    if resp is None or resp.status_code != 200:
        return None
    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
        return None
    video_id = (
        dig(data, "replacementEndpoint", "reelWatchEndpoint", "videoId")
        or _find_reel_video_id(data)
    )
    if not video_id:
        return None
    logger.info("GET /shorts overlay: videoId=%s", video_id)
    return {"video_id": video_id, "title": "", "channel_id": "", "channel_title": ""}


def _find_reel_video_id(node, depth: int = 0) -> str | None:
    if depth > 12 or not node:
        return None
    if isinstance(node, dict):
        if "reelWatchEndpoint" in node:
            vid = node["reelWatchEndpoint"].get("videoId")
            if vid:
                return vid
        for v in node.values():
            r = _find_reel_video_id(v, depth + 1)
            if r:
                return r
    elif isinstance(node, list):
        for item in node:
            r = _find_reel_video_id(item, depth + 1)
            if r:
                return r
    return None


# ── Keyword search fallback ───────────────────────────────────────────────────

def _search_candidates(client: YouTubeClient, keyword: str) -> list[dict]:
    resp = client.get(
        "https://www.youtube.com/results",
        params={"search_query": keyword, "sp": SP_LAST_HOUR_SORT_NEW, "hl": "zh-TW"},
    )
    if resp is None or resp.status_code != 200:
        return []
    data = extract_js_var(resp.text, "ytInitialData")
    if not data:
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
                "video_id": video_id,
                "title": title,
                "channel_id": channel_id,
                "channel_title": channel_title,
            })

    logger.info("search '%s': %d candidates", keyword, len(results))
    return results
