"""
從三種來源收集影片 ID，寫入 state.db。

  collect_trending()       每 15 min 呼叫一次
  collect_from_search()    每 1 h 呼叫一次
  collect_from_channels()  每 1 h 呼叫一次
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from src.crawler.fetch_channel_uploads import fetch_channel_uploads
from src.crawler.fetch_explore import fetch_explore
from src.crawler.fetch_search import fetch_search
from src.crawler.keyword_generator import generate_keywords, _load_trending_tags
from src.utils.http_client import YouTubeClient
from src.utils.io import load_json_dict
from src.utils.state_db import StateDB
from src.utils.time import format_iso, now_utc

logger = logging.getLogger(__name__)

_SEARCH_KEYWORDS_PER_HOUR = 7   # keyword lookups per collect_from_search() call
_SEARCH_TARGET_PER_HOUR = 10    # target new videos from search
_CHANNEL_TARGET_PER_HOUR = 5    # target new videos from channels


def collect_explore(client: YouTubeClient, db: StateDB) -> int:
    """Fetch videos from YouTube Explore categories (multi-region) and register new ones."""
    now = format_iso(now_utc())
    videos = fetch_explore(client, max_per_category=random.randint(3, 5))
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


def collect_from_channels(client: YouTubeClient, db: StateDB) -> int:
    """Check tracked channels for new uploads. Returns count of new videos."""
    now = format_iso(now_utc())
    channels = list(db.get_tracked_channels())
    if not channels:
        return 0

    random.shuffle(channels)
    new_count = 0

    for ch in channels:
        if new_count >= _CHANNEL_TARGET_PER_HOUR:
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
