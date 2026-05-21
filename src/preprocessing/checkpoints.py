"""
從清理後的時序資料抽出固定時間點（3h / 48h / 72h 等）的觀測值。

label / regression dataset / 表格特徵都會用到「在時間 T 時的累積指標」，
這支模組統一提供抽樣邏輯，避免重複實作 + 防資料洩漏（每個任務只能用允許窗口）。

抽樣策略：取「最接近目標時刻、誤差不超過 tolerance」的最後一筆 snapshot。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 預設容忍誤差：0–3h 取樣 10 min 間隔，3h+ 取樣 2h 間隔，所以分段給不同 tol
DEFAULT_TOLERANCE_MIN = {
    60.0:   15.0,   # 1h ± 15 min
    180.0:  20.0,   # 3h ± 20 min
    2880.0: 90.0,   # 48h ± 1.5h
    4320.0: 120.0,  # 72h ± 2h
}


@dataclass
class CheckpointSpec:
    name: str          # 欄位前綴，例如 "3h", "48h"
    target_min: float  # 目標分鐘數
    tolerance_min: float | None = None


def snapshot_at(
    ts: pd.DataFrame,
    target_min: float,
    tolerance_min: float | None = None,
) -> pd.DataFrame:
    """
    對每支影片，取最接近 target_min 的一筆 snapshot。
    超過 tolerance_min 的影片該行回 NaN（caller 自行決定要不要丟）。

    回傳欄位：video_id + view_count / like_count / comment_count / subscriber_count
              + time_since_publish_minutes（實際對到的時間）
    """
    if ts.empty:
        return pd.DataFrame(columns=[
            "video_id", "view_count", "like_count", "comment_count",
            "subscriber_count", "time_since_publish_minutes",
        ])
    if tolerance_min is None:
        tolerance_min = DEFAULT_TOLERANCE_MIN.get(target_min, 30.0)

    df = ts[["video_id", "time_since_publish_minutes", "view_count",
             "like_count", "comment_count", "subscriber_count"]].copy()
    df["_diff"] = (df["time_since_publish_minutes"] - target_min).abs()
    df = df[df["_diff"] <= tolerance_min]

    idx = df.groupby("video_id")["_diff"].idxmin()
    out = df.loc[idx].drop(columns="_diff").reset_index(drop=True)
    return out


def first_snapshot(ts: pd.DataFrame) -> pd.DataFrame:
    """每支影片的最早一筆 snapshot（用來取 subscriber_count_at_publish）。"""
    if ts.empty:
        return pd.DataFrame(columns=ts.columns)
    df = ts.sort_values(["video_id", "time_since_publish_minutes"])
    return df.groupby("video_id", as_index=False).first()


def collect_checkpoints(
    ts: pd.DataFrame,
    specs: list[CheckpointSpec],
) -> pd.DataFrame:
    """
    對多個目標時刻同時抽樣，回傳 wide-format DataFrame：
    一支影片一列，每個 spec 產生 {name}_view_count, {name}_like_count, ... 欄位。
    """
    if ts.empty:
        return pd.DataFrame(columns=["video_id"])

    base = pd.DataFrame({"video_id": ts["video_id"].unique()})
    for spec in specs:
        snap = snapshot_at(ts, spec.target_min, spec.tolerance_min)
        snap = snap.rename(columns={
            "view_count":      f"views_{spec.name}",
            "like_count":      f"likes_{spec.name}",
            "comment_count":   f"comments_{spec.name}",
            "subscriber_count": f"subs_{spec.name}",
            "time_since_publish_minutes": f"actual_min_{spec.name}",
        })
        base = base.merge(snap, on="video_id", how="left")

    return base
