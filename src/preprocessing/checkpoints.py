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


_VALUE_COLS = ["view_count", "like_count", "comment_count", "subscriber_count"]


@dataclass
class CheckpointSpec:
    name: str          # 欄位前綴，例如 "3h", "48h"
    target_min: float  # 目標分鐘數
    tolerance_min: float | None = None
    # ── 插值模式（累積型單調指標適用）────────────────────────────────────
    # interpolate=True 時，改用「target 前後最近兩筆線性插值到 target」，
    # 而非取容差內最近的單筆。取樣稀疏時命中率大幅提升，且端點值更精確。
    # max_before_min / max_after_min 限制插值用的前/後點距 target 的最大距離，
    # 避免長距離外插誤差。特別注意 after 距離會用到 target 之後的資料，
    # 對「只能用 0–T 窗口」的特徵點（如 3h）必須收緊 max_after_min 以防洩漏。
    interpolate: bool = False
    max_before_min: float | None = None
    max_after_min: float | None = None


def snapshot_at(
    ts: pd.DataFrame,
    target_min: float,
    tolerance_min: float | None = None,
    interpolate: bool = False,
    max_before_min: float | None = None,
    max_after_min: float | None = None,
) -> pd.DataFrame:
    """
    對每支影片取 target_min 時刻的觀測值。

    interpolate=False（預設）：取容差內最接近 target 的單筆 snapshot。
    interpolate=True：取 target 前後最近兩筆對數值欄位線性插值到 target；
        若 target 之後無點但 target 之前有點落在容差內，退回用該前點。

    回傳欄位：video_id + view_count / like_count / comment_count / subscriber_count
              + time_since_publish_minutes（容差模式為實際對到的時間，插值模式為 target_min）
    """
    cols = ["video_id", "view_count", "like_count", "comment_count",
            "subscriber_count", "time_since_publish_minutes"]
    if ts.empty:
        return pd.DataFrame(columns=cols)
    if tolerance_min is None:
        tolerance_min = DEFAULT_TOLERANCE_MIN.get(target_min, 30.0)

    if not interpolate:
        df = ts[["video_id", "time_since_publish_minutes", *_VALUE_COLS]].copy()
        df["_diff"] = (df["time_since_publish_minutes"] - target_min).abs()
        df = df[df["_diff"] <= tolerance_min]

        idx = df.groupby("video_id")["_diff"].idxmin()
        out = df.loc[idx].drop(columns="_diff").reset_index(drop=True)
        return out

    return _interpolated_snapshot(
        ts, target_min, tolerance_min, max_before_min, max_after_min
    )


def _interpolated_snapshot(
    ts: pd.DataFrame,
    target_min: float,
    tolerance_min: float,
    max_before_min: float | None,
    max_after_min: float | None,
) -> pd.DataFrame:
    """對每支影片線性插值到 target_min。見 snapshot_at 說明。"""
    df = ts[["video_id", "time_since_publish_minutes", *_VALUE_COLS]].copy()
    df = df.dropna(subset=["time_since_publish_minutes"])
    df = df.sort_values(["video_id", "time_since_publish_minutes"])

    records: list[dict] = []
    for vid, g in df.groupby("video_id", sort=False):
        t = g["time_since_publish_minutes"].to_numpy(dtype=float)
        before_pos = np.searchsorted(t, target_min, side="right") - 1
        after_pos = np.searchsorted(t, target_min, side="left")

        has_before = before_pos >= 0
        has_after = after_pos < len(t)
        # after_pos 可能正好落在等於 target 的點上
        exact = has_after and t[after_pos] == target_min

        if exact:
            row = g.iloc[after_pos]
            rec = {c: row[c] for c in _VALUE_COLS}
        elif has_before and has_after:
            i, j = before_pos, after_pos
            gap_before = target_min - t[i]
            gap_after = t[j] - target_min
            if max_before_min is not None and gap_before > max_before_min:
                continue
            if max_after_min is not None and gap_after > max_after_min:
                # 後點太遠：退回容差內前點
                if gap_before <= tolerance_min:
                    rec = {c: g.iloc[i][c] for c in _VALUE_COLS}
                else:
                    continue
            else:
                w = (target_min - t[i]) / (t[j] - t[i])
                lo, hi = g.iloc[i], g.iloc[j]
                rec = {c: lo[c] + (hi[c] - lo[c]) * w for c in _VALUE_COLS}
        elif has_before and (target_min - t[before_pos]) <= tolerance_min:
            rec = {c: g.iloc[before_pos][c] for c in _VALUE_COLS}
        else:
            continue

        rec["video_id"] = vid
        rec["time_since_publish_minutes"] = target_min
        records.append(rec)

    if not records:
        return pd.DataFrame(columns=[
            "video_id", *_VALUE_COLS, "time_since_publish_minutes",
        ])
    return pd.DataFrame.from_records(records)


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
        snap = snapshot_at(
            ts, spec.target_min, spec.tolerance_min,
            interpolate=spec.interpolate,
            max_before_min=spec.max_before_min,
            max_after_min=spec.max_after_min,
        )
        snap = snap.rename(columns={
            "view_count":      f"views_{spec.name}",
            "like_count":      f"likes_{spec.name}",
            "comment_count":   f"comments_{spec.name}",
            "subscriber_count": f"subs_{spec.name}",
            "time_since_publish_minutes": f"actual_min_{spec.name}",
        })
        base = base.merge(snap, on="video_id", how="left")

    return base
