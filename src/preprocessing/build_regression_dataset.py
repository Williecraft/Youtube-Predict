"""
回歸任務資料集。對應 PROJECT_CONTEXT.md §5。

每支影片有 48h 輸入端點 + 72h target 端點就建一筆 sample：
    sample_id          = "{video_id}_first48h"
    input window       = [publish_time, publish_time + 48h]
    target window      = (publish_time + 48h, publish_time + 72h]
    next_24h_views     = max(views_72h - views_48h, 0)
    log_next_24h_views = log1p(next_24h_views)

防洩漏（§11 規則 2/4）：
    - 0–48h 內資料可入 feature（48h 當下累積 views 允許）
    - views_72h / next_24h_views / log_next_24h_views 只能當 target

輸出兩個檔案：
    regression_dataset.csv      sample 級 metadata + target
    regression_features_48h.csv sample 級 features（從 0–48h 窗口萃取）
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.preprocessing.checkpoints import (
    CheckpointSpec,
    collect_checkpoints,
    first_snapshot,
)
from src.preprocessing.clean_timeseries import load_clean_timeseries
from src.preprocessing.load_raw import load_videos_static
from src.preprocessing.paths import (
    REGRESSION_DATASET_CSV,
    REGRESSION_FEATURES_CSV,
    ensure_processed_dirs,
)

logger = logging.getLogger(__name__)


def build_regression(
    ts: pd.DataFrame | None = None,
    static: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳 (regression_dataset, regression_features_48h)。"""
    if ts is None:
        ts = load_clean_timeseries()
    if static is None:
        static = load_videos_static()

    if ts.empty or static.empty:
        empty = pd.DataFrame()
        return empty, empty

    # ── checkpoints：1h / 3h / 24h / 48h / 72h ────────────────────────────
    cps = collect_checkpoints(ts, [
        CheckpointSpec("1h",  target_min=60.0),
        CheckpointSpec("3h",  target_min=180.0),
        CheckpointSpec("24h", target_min=1440.0, tolerance_min=60.0),
        CheckpointSpec("48h", target_min=2880.0),
        CheckpointSpec("72h", target_min=4320.0),
    ])

    first = first_snapshot(ts)[["video_id", "subscriber_count"]].rename(
        columns={"subscriber_count": "subscriber_count_at_publish"}
    )

    s = static[[
        "video_id", "channel_id", "publish_time", "duration_seconds",
        "category", "is_shorts", "title_length", "tag_count",
    ]].copy()
    s["publish_time"] = pd.to_datetime(s["publish_time"], utc=True, errors="coerce")
    s["publish_hour"] = s["publish_time"].dt.hour
    s["is_shorts"] = s["is_shorts"].fillna(False).astype(bool)

    df = s.merge(first, on="video_id", how="left").merge(cps, on="video_id", how="left")

    # ── §3 step 9：缺 48h 輸入端點或 72h target 端點的影片排除 ────────────
    before = len(df)
    df = df.dropna(subset=["views_48h", "views_72h"])
    logger.info("依 views_48h / views_72h 過濾：%d → %d 支影片", before, len(df))

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df["sample_id"] = df["video_id"] + "_first48h"

    # ── target ─────────────────────────────────────────────────────────
    df["next_24h_views"]     = (df["views_72h"] - df["views_48h"]).clip(lower=0)
    df["log_next_24h_views"] = np.log1p(df["next_24h_views"])

    # ── dataset metadata 表（PROJECT_CONTEXT.md §5 至少欄位）─────────────
    dataset_cols = [
        "sample_id", "video_id", "channel_id", "publish_time",
        "input_window_start_h", "input_window_end_h",
        "target_window_start_h", "target_window_end_h",
        "views_48h", "views_72h",
        "next_24h_views", "log_next_24h_views",
    ]
    df["input_window_start_h"]  = 0
    df["input_window_end_h"]    = 48
    df["target_window_start_h"] = 48
    df["target_window_end_h"]   = 72
    regression_dataset = df[dataset_cols].copy()

    # ── features（0–48h 內可用的所有訊號）──────────────────────────────
    df["subscriber_count_at_publish"] = df["subscriber_count_at_publish"].fillna(0)
    df["log_subscriber_count"] = np.log1p(df["subscriber_count_at_publish"])

    df["log_views_1h"]  = np.log1p(df["views_1h"].fillna(0))
    df["log_views_3h"]  = np.log1p(df["views_3h"].fillna(0))
    df["log_views_24h"] = np.log1p(df["views_24h"].fillna(0))
    df["log_views_48h"] = np.log1p(df["views_48h"])

    df["growth_1h_to_3h"]    = (df["views_3h"]  - df["views_1h"]).clip(lower=0)
    df["growth_3h_to_24h"]   = (df["views_24h"] - df["views_3h"]).clip(lower=0)
    df["growth_24h_to_48h"]  = (df["views_48h"] - df["views_24h"]).clip(lower=0)
    df["rate_late_to_early"] = (
        df["growth_24h_to_48h"] / df["growth_1h_to_3h"].clip(lower=1)
    )

    df["like_view_ratio_48h"]    = df["likes_48h"].fillna(0)    / df["views_48h"].clip(lower=1)
    df["comment_view_ratio_48h"] = df["comments_48h"].fillna(0) / df["views_48h"].clip(lower=1)
    df["engagement_rate_48h"] = (
        (df["likes_48h"].fillna(0) + df["comments_48h"].fillna(0))
        / df["views_48h"].clip(lower=1)
    )

    feature_cols = [
        "sample_id", "video_id", "channel_id", "publish_time",
        "duration_seconds", "category", "publish_hour",
        "is_shorts", "title_length", "tag_count",
        "subscriber_count_at_publish", "log_subscriber_count",
        # 0–48h 累積快照
        "views_1h", "views_3h", "views_24h", "views_48h",
        "log_views_1h", "log_views_3h", "log_views_24h", "log_views_48h",
        # 區段成長
        "growth_1h_to_3h", "growth_3h_to_24h", "growth_24h_to_48h",
        "rate_late_to_early",
        # 互動率
        "likes_48h", "comments_48h",
        "like_view_ratio_48h", "comment_view_ratio_48h", "engagement_rate_48h",
    ]
    regression_features = df[feature_cols].copy()

    return regression_dataset, regression_features


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ensure_processed_dirs()
    dataset, features = build_regression()
    dataset.to_csv(REGRESSION_DATASET_CSV, index=False)
    features.to_csv(REGRESSION_FEATURES_CSV, index=False)
    logger.info("regression_dataset  → %s（%d 列）", REGRESSION_DATASET_CSV, len(dataset))
    logger.info("regression_features → %s（%d 列）", REGRESSION_FEATURES_CSV, len(features))


if __name__ == "__main__":
    main()
