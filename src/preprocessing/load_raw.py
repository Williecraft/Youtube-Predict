"""
讀取爬蟲產出的原始資料，回傳結構化 pandas DataFrame / dict。

對應 PROJECT_CONTEXT.md §3 step 1（合併 static / timeseries / comments）。
本模組只做 IO，不做清理、不算特徵；下游模組（clean_timeseries、build_labels 等）
拿到的是「結構正確、欄位齊全、但內容未驗證」的 DataFrame。

主要函式
--------
- load_videos_static()  → pd.DataFrame（一支影片一列）
- load_channel_static() → pd.DataFrame（一個頻道一列）
- load_timeseries(video_ids=None) → pd.DataFrame（多支影片串接）
- load_comments(video_ids=None)   → pd.DataFrame（多支影片串接，含 snapshot_label）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.preprocessing.paths import (
    CHANNEL_STATIC_JSON,
    COMMENTS_DIR,
    TIMESERIES_DIR,
    VIDEOS_STATIC_JSON,
)
from src.utils.io import load_json_dict, read_jsonl

logger = logging.getLogger(__name__)

# Canonical column orders — 下游可以依賴這個順序
VIDEOS_STATIC_COLUMNS = [
    "video_id", "title", "title_length", "channel_id", "publish_time",
    "duration_seconds", "category", "tags", "tag_count",
    "is_shorts", "shorts_status_code", "shorts_checked_at",
    "subscriber_count_at_fetch", "comment_count_at_fetch",
    "video_status", "discovery_source", "static_fetched_at",
]

CHANNEL_STATIC_COLUMNS = [
    "channel_id", "channel_title", "subscriber_count",
    "subscriber_count_checked_at", "country", "discovered_at",
    "discovered_via_video_id", "last_checked_at", "last_new_video_at",
]

TIMESERIES_COLUMNS = [
    "video_id", "crawl_time", "time_since_publish_minutes",
    "view_count", "like_count", "comment_count",
    "subscriber_count", "video_status",
]

COMMENT_COLUMNS = [
    "video_id", "snapshot_label", "comment_id",
    "comment_text", "comment_like_count", "comment_published_at", "crawl_time",
]


def load_videos_static() -> pd.DataFrame:
    """讀取 videos_static.json（dict 結構）→ DataFrame。"""
    raw = load_json_dict(VIDEOS_STATIC_JSON)
    if not raw:
        logger.warning("videos_static.json 不存在或為空：%s", VIDEOS_STATIC_JSON)
        return pd.DataFrame(columns=VIDEOS_STATIC_COLUMNS)

    df = pd.DataFrame.from_records(list(raw.values()))
    # 補齊缺欄位（不同時期爬到的紀錄可能欄位不齊）
    for col in VIDEOS_STATIC_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[VIDEOS_STATIC_COLUMNS]


def load_channel_static() -> pd.DataFrame:
    """讀取 channel_static.json → DataFrame。"""
    raw = load_json_dict(CHANNEL_STATIC_JSON)
    if not raw:
        logger.warning("channel_static.json 不存在或為空：%s", CHANNEL_STATIC_JSON)
        return pd.DataFrame(columns=CHANNEL_STATIC_COLUMNS)

    df = pd.DataFrame.from_records(list(raw.values()))
    for col in CHANNEL_STATIC_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[CHANNEL_STATIC_COLUMNS]


def _iter_timeseries_files(video_ids: Iterable[str] | None) -> list[Path]:
    if not TIMESERIES_DIR.exists():
        return []
    if video_ids is None:
        return sorted(TIMESERIES_DIR.glob("*.csv"))
    return [TIMESERIES_DIR / f"{vid}.csv" for vid in video_ids
            if (TIMESERIES_DIR / f"{vid}.csv").exists()]


def load_timeseries(video_ids: Iterable[str] | None = None) -> pd.DataFrame:
    """
    讀取 by_video/*.csv 並串接成單一 DataFrame。

    video_ids=None 時讀全部；否則只讀指定影片，避免一口氣讀數萬支。
    """
    files = _iter_timeseries_files(video_ids)
    if not files:
        logger.warning("沒有 timeseries 檔案可讀：%s", TIMESERIES_DIR)
        return pd.DataFrame(columns=TIMESERIES_COLUMNS)

    frames = []
    for fp in files:
        try:
            df = pd.read_csv(fp)
        except (pd.errors.EmptyDataError, FileNotFoundError):
            continue
        if df.empty:
            continue
        # 補齊缺欄位
        for col in TIMESERIES_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        frames.append(df[TIMESERIES_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=TIMESERIES_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _iter_comment_files(video_ids: Iterable[str] | None) -> list[Path]:
    if not COMMENTS_DIR.exists():
        return []
    if video_ids is None:
        return sorted(COMMENTS_DIR.glob("*_t*h.jsonl"))
    out = []
    for vid in video_ids:
        for label in ("t1h", "t2h", "t3h"):
            fp = COMMENTS_DIR / f"{vid}_{label}.jsonl"
            if fp.exists():
                out.append(fp)
    return out


def load_comments(video_ids: Iterable[str] | None = None) -> pd.DataFrame:
    """
    讀取留言 JSONL，從檔名拆出 video_id 與 snapshot_label，串接成 DataFrame。

    注意：comments JSONL 內每筆 record 沒有 video_id 欄位（爬蟲沒寫），
    必須靠檔名取得；本函式負責補回去。
    """
    files = _iter_comment_files(video_ids)
    if not files:
        logger.warning("沒有 comment 檔案可讀：%s", COMMENTS_DIR)
        return pd.DataFrame(columns=COMMENT_COLUMNS)

    frames = []
    for fp in files:
        # 檔名格式：{video_id}_{t1h|t2h|t3h}.jsonl
        stem = fp.stem
        if "_t" not in stem:
            continue
        video_id, snap = stem.rsplit("_", 1)
        records = read_jsonl(fp)
        if not records:
            continue
        df = pd.DataFrame.from_records(records)
        df["video_id"] = video_id
        if "snapshot_label" not in df.columns:
            df["snapshot_label"] = snap
        for col in COMMENT_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        frames.append(df[COMMENT_COLUMNS])

    if not frames:
        return pd.DataFrame(columns=COMMENT_COLUMNS)
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    vs = load_videos_static()
    cs = load_channel_static()
    ts = load_timeseries()
    cm = load_comments()
    print(f"videos_static : {len(vs):>7} rows")
    print(f"channel_static: {len(cs):>7} rows")
    print(f"timeseries    : {len(ts):>7} rows  ({ts['video_id'].nunique() if not ts.empty else 0} videos)")
    print(f"comments      : {len(cm):>7} rows  ({cm['video_id'].nunique() if not cm.empty else 0} videos)")
