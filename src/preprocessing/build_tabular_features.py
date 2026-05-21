"""
建立分類任務的表格特徵 tabular_features.csv。對應 PROJECT_CONTEXT.md §6。

允許使用的資料窗口：發布後 0–3h（防洩漏，§11 規則 1）。

特徵分組（feature group A/B 對應 PROJECT_CONTEXT.md §10）：
  A 影片基本 + 頻道
      duration_seconds, category, publish_hour, is_shorts, title_length, tag_count,
      log_subscriber_count
  B 早期流量（A + 以下）
      views_1h, views_3h, likes_3h, comments_3h,
      view_delta_0h_1h, view_delta_1h_3h,
      view_growth_rate_1h, views_per_minute_early,
      engagement_rate_early, like_view_ratio_3h, comment_view_ratio_3h

留言情緒特徵（C1/C2/C3）由 build_comment_emotion_features.py 產出，
本檔只負責 A + B；下游合併。
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
from src.preprocessing.paths import TABULAR_FEATURES_CSV, ensure_processed_dirs

logger = logging.getLogger(__name__)


def build_tabular_features(
    ts: pd.DataFrame | None = None,
    static: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if ts is None:
        ts = load_clean_timeseries()
    if static is None:
        static = load_videos_static()

    if ts.empty or static.empty:
        logger.warning("輸入空，build_tabular_features 回傳空 DataFrame")
        return pd.DataFrame()

    # ── checkpoints：1h、3h（防洩漏：不取 48h、72h）─────────────────────
    cps = collect_checkpoints(ts, [
        CheckpointSpec("0h", target_min=0.0,   tolerance_min=15.0),
        CheckpointSpec("1h", target_min=60.0),
        CheckpointSpec("3h", target_min=180.0),
    ])

    # ── 第一筆 snapshot 拿 subscriber_count_at_publish ─────────────────
    first = first_snapshot(ts)[["video_id", "subscriber_count"]].rename(
        columns={"subscriber_count": "subscriber_count_at_publish"}
    )

    # ── 靜態欄位 ───────────────────────────────────────────────────────
    s = static[[
        "video_id", "channel_id", "publish_time", "duration_seconds",
        "category", "is_shorts", "title_length", "tag_count",
    ]].copy()
    s["publish_time"] = pd.to_datetime(s["publish_time"], utc=True, errors="coerce")
    s["publish_hour"] = s["publish_time"].dt.hour
    s["is_shorts"] = s["is_shorts"].fillna(False).astype(bool)

    df = s.merge(first, on="video_id", how="left").merge(cps, on="video_id", how="left")

    # ── A 組：頻道 ─────────────────────────────────────────────────────
    df["subscriber_count_at_publish"] = df["subscriber_count_at_publish"].fillna(0)
    df["log_subscriber_count"] = np.log1p(df["subscriber_count_at_publish"])

    # ── B 組：早期流量（防洩漏：用 0/1/3h，不用 48/72h）────────────────
    df["views_0h"] = df.get("views_0h", pd.Series(dtype="float64")).fillna(0)
    df["views_1h"] = df["views_1h"].fillna(0)
    df["views_3h"] = df["views_3h"].fillna(0)
    df["likes_3h"] = df["likes_3h"].fillna(0)
    df["comments_3h"] = df["comments_3h"].fillna(0)

    df["view_delta_0h_1h"] = (df["views_1h"] - df["views_0h"]).clip(lower=0)
    df["view_delta_1h_3h"] = (df["views_3h"] - df["views_1h"]).clip(lower=0)
    df["view_growth_rate_1h"] = df["views_1h"] / df["views_0h"].clip(lower=1)
    df["views_per_minute_early"] = df["views_3h"] / 180.0

    df["like_view_ratio_3h"]    = df["likes_3h"]    / df["views_3h"].clip(lower=1)
    df["comment_view_ratio_3h"] = df["comments_3h"] / df["views_3h"].clip(lower=1)
    df["engagement_rate_early"] = (
        (df["likes_3h"] + df["comments_3h"]) / df["views_3h"].clip(lower=1)
    )

    # ── log1p 衍生（PROJECT_CONTEXT.md §3 step 10）─────────────────────
    df["log_views_3h"]    = np.log1p(df["views_3h"])
    df["log_likes_3h"]    = np.log1p(df["likes_3h"])
    df["log_comments_3h"] = np.log1p(df["comments_3h"])

    feat_cols = [
        # join keys
        "video_id", "channel_id", "publish_time",
        # A
        "duration_seconds", "category", "publish_hour",
        "is_shorts", "title_length", "tag_count",
        "subscriber_count_at_publish", "log_subscriber_count",
        # B
        "views_1h", "views_3h", "likes_3h", "comments_3h",
        "view_delta_0h_1h", "view_delta_1h_3h",
        "view_growth_rate_1h", "views_per_minute_early",
        "like_view_ratio_3h", "comment_view_ratio_3h", "engagement_rate_early",
        "log_views_3h", "log_likes_3h", "log_comments_3h",
    ]
    return df[feat_cols]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ensure_processed_dirs()
    df = build_tabular_features()
    df.to_csv(TABULAR_FEATURES_CSV, index=False)
    logger.info("tabular_features 寫入 %s（%d 列）", TABULAR_FEATURES_CSV, len(df))


if __name__ == "__main__":
    main()
