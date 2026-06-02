"""
建立分類標籤 label_dataset.csv。對應 PROJECT_CONTEXT.md §4。

公式：
    effective_subscriber_count = max(subscriber_count_at_publish, 1000)
    audience_normalized_views_48h = views_48h / effective_subscriber_count
    viral_score_48h = log1p(views_48h) - log1p(effective_subscriber_count)
    min_abs_views_48h = 10000 if is_shorts else 2000
    viral_view_threshold_48h = max(min_abs_views_48h, 2 * effective_subscriber_count)
    is_viral_48h = views_48h >= viral_view_threshold_48h

爆紅分級：
    non_viral   < 1.0x
    strong      1.0x – 2.0x
    viral       2.0x – 5.0x  且達 min_abs_views_48h
    super_viral >= 5.0x       且達 min_abs_views_48h

baseline：
    growth_rate_48h = views_48h / max(views_3h, 1)
    is_high_growth_48h = growth_rate_48h >= median(growth_rate_48h on train)
        （但 median 必須由 split_dataset.py 或 modeling 階段用 train 算，
        本檔不寫 is_high_growth_48h；只輸出 growth_rate_48h。）

PROJECT_CONTEXT.md §3 step 7/8：缺 0–3h 主要序列或 48h label 的影片排除。
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
from src.preprocessing.paths import LABEL_DATASET_CSV, ensure_processed_dirs

logger = logging.getLogger(__name__)

MIN_ABS_VIEWS_LONG   = 200
MIN_ABS_VIEWS_SHORTS = 1000
SUBSCRIBER_FLOOR     = 1000


def build_labels(
    ts: pd.DataFrame | None = None,
    static: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if ts is None:
        ts = load_clean_timeseries()
    if static is None:
        static = load_videos_static()

    if ts.empty or static.empty:
        logger.warning("輸入空，build_labels 回傳空 DataFrame")
        return pd.DataFrame()

    # 1. 取 3h / 48h 兩個檢查點
    cps = collect_checkpoints(ts, [
        CheckpointSpec("3h", target_min=180.0),
        CheckpointSpec("48h", target_min=2880.0),
    ])

    # 2. subscriber_count_at_publish 從每支影片第一筆 timeseries 取
    first = first_snapshot(ts)[["video_id", "subscriber_count"]].rename(
        columns={"subscriber_count": "subscriber_count_at_publish"}
    )

    # 3. 串接 static.is_shorts / publish_time
    s = static[["video_id", "is_shorts", "publish_time", "channel_id"]].copy()

    df = cps.merge(first, on="video_id", how="left").merge(s, on="video_id", how="left")

    # 4. PROJECT_CONTEXT.md §3 step 7/8：缺 0–3h 主序列或 48h 端點的影片排除
    before = len(df)
    df = df.dropna(subset=["views_3h", "views_48h"])
    logger.info("依 views_3h / views_48h 過濾：%d → %d 支影片", before, len(df))

    # 訂閱數補預設值（極早期影片可能拿不到）
    df["subscriber_count_at_publish"] = df["subscriber_count_at_publish"].fillna(0)

    # 5. 標籤公式
    df["effective_subscriber_count"] = df["subscriber_count_at_publish"].clip(lower=SUBSCRIBER_FLOOR)
    df["audience_normalized_views_48h"] = df["views_48h"] / df["effective_subscriber_count"]
    df["viral_score_48h"] = np.log1p(df["views_48h"]) - np.log1p(df["effective_subscriber_count"])

    df["is_shorts"] = df["is_shorts"].fillna(False).astype(bool)
    df["min_abs_views_48h"] = np.where(df["is_shorts"], MIN_ABS_VIEWS_SHORTS, MIN_ABS_VIEWS_LONG)
    df["viral_view_threshold_48h"] = np.maximum(
        df["min_abs_views_48h"],
        0.5 * df["effective_subscriber_count"],
    )
    df["is_viral_48h"] = (df["views_48h"] >= df["viral_view_threshold_48h"]).astype(int)

    # 6. 爆紅分級
    ratio = df["audience_normalized_views_48h"]
    meets_min = df["views_48h"] >= df["min_abs_views_48h"]
    df["viral_level_48h"] = pd.Series("non_viral", index=df.index)
    df.loc[ratio >= 1.0, "viral_level_48h"] = "strong"
    df.loc[(ratio >= 2.0) & meets_min, "viral_level_48h"] = "viral"
    df.loc[(ratio >= 5.0) & meets_min, "viral_level_48h"] = "super_viral"

    # 7. baseline growth_rate（is_high_growth_48h 需 train median，留給 split 階段）
    df["growth_rate_48h"] = df["views_48h"] / df["views_3h"].clip(lower=1)

    out_cols = [
        "video_id", "channel_id", "is_shorts", "publish_time",
        "views_3h", "views_48h",
        "subscriber_count_at_publish", "effective_subscriber_count",
        "min_abs_views_48h", "viral_view_threshold_48h",
        "audience_normalized_views_48h", "viral_score_48h",
        "is_viral_48h", "viral_level_48h",
        "growth_rate_48h",
    ]
    return df[out_cols]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ensure_processed_dirs()
    df = build_labels()
    df.to_csv(LABEL_DATASET_CSV, index=False)
    logger.info("label_dataset 寫入 %s（%d 列, 爆紅率 %.2f%%）",
                LABEL_DATASET_CSV, len(df),
                100 * df["is_viral_48h"].mean() if len(df) else 0)


if __name__ == "__main__":
    main()
