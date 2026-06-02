"""
從四種來源收集影片 ID，寫入 state.db。

  collect_explore()         每 15 min 呼叫一次
  collect_from_shorts()     每 1 h 呼叫一次
  collect_from_search()     每 1 h 呼叫一次
  collect_from_channels()   每 1 h 呼叫一次
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from src.crawler.fetch_channel_uploads import fetch_channel_uploads
import re

from src.crawler.fetch_explore import fetch_explore
from src.crawler.fetch_search import SP_LAST_HOUR_SORT_NEW, fetch_search
from src.crawler.fetch_shorts_page import fetch_shorts_page
from src.crawler.keyword_generator import generate_keywords, _load_trending_tags
from src.utils.http_client import YouTubeClient
from src.utils.io import load_json_dict
from src.utils.state_db import StateDB
from src.utils.time import format_iso, now_utc

logger = logging.getLogger(__name__)

_SEARCH_KEYWORDS_PER_HOUR = 4   # keyword lookups per collect_from_search() call
_SEARCH_TARGET_PER_HOUR = 5     # target new videos from search
_CHANNEL_TARGET_PER_CALL = 15   # target new videos per channel-poll call (every 10 min)
_SHORTS_TARGET_PER_RUN = 10     # cap new Shorts per poll so static fetch can keep up
_FRESH_SEARCH_KEYWORDS = 3      # keyword lookups per collect_from_fresh_search() call
_FRESH_SEARCH_TARGET = 2        # target very-fresh (≤5 min uploaded) videos per call
_FRESH_MAX_AGE_MIN = 5          # only accept videos uploaded within this many minutes

# Matches relative-time strings YouTube returns in zh-TW like "3 分鐘前", "剛剛", "30 秒前"
_RE_SEC  = re.compile(r"(\d+)\s*秒")
_RE_MIN  = re.compile(r"(\d+)\s*分")


def _is_very_fresh(published_time_text: str, max_min: int = _FRESH_MAX_AGE_MIN) -> bool:
    """Return True if the relative time text indicates an actual upload within max_min minutes.

    Rejects:
      - "預定時間" / "首播" / "直播" prefixes (scheduled streams or premieres — not real uploads)
      - empty strings
    """
    s = published_time_text or ""
    if not s:
        return False
    # Exclude scheduled streams / premieres / live indicators
    for marker in ("預定時間", "预定时间", "首播", "首发", "直播中", "正在直播"):
        if marker in s:
            return False
    if "剛剛" in s or "刚刚" in s:
        return True
    if _RE_SEC.search(s):
        return True
    m = _RE_MIN.search(s)
    if m:
        try:
            return int(m.group(1)) <= max_min
        except ValueError:
            return False
    return False


def collect_explore(client: YouTubeClient, db: StateDB) -> int:
    """Fetch videos from YouTube Explore categories (multi-region) and register new ones."""
    now = format_iso(now_utc())
    videos = fetch_explore(client, max_per_category=random.randint(1, 2))
    new_count = 0
    for v in videos:
        added = db.add_video(
            video_id=v["video_id"],
            source="explore",
            source_detail=f"{v.get('region','')}/{v.get('category','')}",
            discovered_at=now,
        )
        if added:
            new_count += 1
            logger.info("new explore video: %s (%s)", v["video_id"], v.get("title", "")[:50])
        if v.get("channel_id"):
            db.upsert_channel(
                v["channel_id"],
                channel_title=v.get("channel_title", ""),
                discovered_at=now,
                discovered_via_video_id=v["video_id"],
            )
    logger.info("collect_explore: %d total, %d new", len(videos), new_count)
    return new_count


def collect_from_shorts(client: YouTubeClient, db: StateDB) -> int:
    """Fetch Shorts candidates, pre-filter via HTTP redirect check, then register confirmed Shorts."""
    from src.crawler.detect_shorts import detect_shorts

    now = format_iso(now_utc())
    # 抓比目標多一些候選，補回被過濾掉的比例
    candidates = fetch_shorts_page(client, max_results=_SHORTS_TARGET_PER_RUN * 8)
    confirmed, skipped, new_count = 0, 0, 0

    for v in candidates:
        if new_count >= _SHORTS_TARGET_PER_RUN:
            break
        vid = v["video_id"]
        # 預先做 HTTP redirect check，非 Shorts 直接丟棄
        result, _ = detect_shorts(client, vid)
        if result != "shorts":
            skipped += 1
            continue
        confirmed += 1
        added = db.add_video(
            video_id=vid,
            source="shorts_page",
            source_detail="shorts_confirmed",
            discovered_at=now,
        )
        if added:
            new_count += 1
            logger.info("new Shorts: %s (%s)", vid, v.get("title", "")[:50])
        if v.get("channel_id"):
            db.upsert_channel(
                v["channel_id"],
                channel_title=v.get("channel_title", ""),
                discovered_at=now,
                discovered_via_video_id=vid,
            )
        client.jitter_sleep(0.3, 0.8)

    logger.info("collect_from_shorts: %d candidates, %d confirmed Shorts, %d new",
                len(candidates), confirmed, new_count)
    return new_count


def collect_from_search(client: YouTubeClient, db: StateDB, data_dir: Path) -> int:
    """Search random keywords and register new videos. Returns count of new videos."""
    now = format_iso(now_utc())
    static_path = data_dir / "raw" / "static" / "videos_static.json"
    trending_tags = _load_trending_tags(static_path)
    keywords = generate_keywords(n=_SEARCH_KEYWORDS_PER_HOUR, trending_tags=trending_tags)

    new_count = 0
    found_this_hour: list[dict] = []

    for kw in keywords:
        if len(found_this_hour) >= _SEARCH_TARGET_PER_HOUR:
            break
        remaining = _SEARCH_TARGET_PER_HOUR - len(found_this_hour)
        results = fetch_search(client, kw, max_results=remaining)
        for v in results:
            vid = v["video_id"]
            if not db.get_video(vid):
                found_this_hour.append(v)
        client.jitter_sleep(1.5, 3.0)

    for v in found_this_hour:
        added = db.add_video(
            video_id=v["video_id"],
            source="search",
            source_detail=v.get("title", "")[:80],
            discovered_at=now,
        )
        if added:
            new_count += 1
        if v.get("channel_id"):
            db.upsert_channel(
                v["channel_id"],
                channel_title=v.get("channel_title", ""),
                discovered_at=now,
                discovered_via_video_id=v["video_id"],
            )

    logger.info("collect_from_search: %d new videos", new_count)
    return new_count


def collect_from_fresh_search(client: YouTubeClient, db: StateDB, data_dir: Path) -> int:
    """Search with 'today + sort by upload date' filter to catch newly uploaded videos.

    Runs more often than collect_from_search to capture videos within minutes of publish.
    """
    now = format_iso(now_utc())
    static_path = data_dir / "raw" / "static" / "videos_static.json"
    trending_tags = _load_trending_tags(static_path)
    keywords = generate_keywords(n=_FRESH_SEARCH_KEYWORDS, trending_tags=trending_tags)

    new_count = 0
    found: list[dict] = []

    for kw in keywords:
        if len(found) >= _FRESH_SEARCH_TARGET:
            break
        # Fetch a larger result set then filter strictly by publish freshness
        results = fetch_search(client, kw, max_results=20, sp=SP_LAST_HOUR_SORT_NEW)
        for v in results:
            if not _is_very_fresh(v.get("published_time_text", "")):
                continue
            vid = v["video_id"]
            if not db.get_video(vid):
                found.append(v)
            if len(found) >= _FRESH_SEARCH_TARGET:
                break
        client.jitter_sleep(1.5, 3.0)

    for v in found:
        added = db.add_video(
            video_id=v["video_id"],
            source="fresh_search",
            source_detail=v.get("title", "")[:80],
            discovered_at=now,
        )
        if added:
            new_count += 1
        if v.get("channel_id"):
            db.upsert_channel(
                v["channel_id"],
                channel_title=v.get("channel_title", ""),
                discovered_at=now,
                discovered_via_video_id=v["video_id"],
            )

    logger.info("collect_from_fresh_search: %d new videos", new_count)
    return new_count


_CHANNEL_MAX_CHECKS_PER_CALL = 50  # cap channels checked per invocation regardless of new-video count


def collect_from_channels(client: YouTubeClient, db: StateDB) -> int:
    """Check tracked channels for new uploads. Returns count of new videos."""
    now = format_iso(now_utc())
    channels = list(db.get_tracked_channels())
    if not channels:
        return 0

    random.shuffle(channels)
    new_count = 0

    for i, ch in enumerate(channels):
        if new_count >= _CHANNEL_TARGET_PER_CALL:
            break
        if i >= _CHANNEL_MAX_CHECKS_PER_CALL:
            break

        channel_id = ch["channel_id"]
        uploads = fetch_channel_uploads(client, channel_id, max_results=3)

        found_new = False
        for v in uploads:
            vid = v["video_id"]
            row = db.get_video(vid)
            if row is None:
                added = db.add_video(
                    video_id=vid,
                    source="channel",
                    source_detail=channel_id,
                    discovered_at=now,
                )
                if added:
                    new_count += 1
                    found_new = True
                    logger.info("new channel video: %s from %s", vid, channel_id)

        db.upsert_channel(
            channel_id,
            last_checked_at=now,
            **({"last_new_video_at": now} if found_new else {}),
        )
        client.jitter_sleep(1.5, 3.0)

    logger.info("collect_from_channels: %d new videos", new_count)
    return new_count
