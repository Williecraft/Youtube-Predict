"""
建立 LSTM 序列特徵。對應 PROJECT_CONTEXT.md §8。

輸出
----
data/processed/sequences_3h/{video_id}.npy
    分類任務用，shape = T × 3，T ≈ 18–36
    features = [view_count, like_count, comment_count]
    取 0–3h 窗口的所有 snapshot

data/processed/sequences_48h/{sample_id}.npy
    回歸任務用，shape = T × 3
    features = [view_count, like_count, comment_count]
    取 0–48h 窗口的所有 snapshot
    sample_id = {video_id}_first48h

正規化：每部影片 / 每個 sample 內，各維度除以該維度在該視窗內的最大值；
       最大值 0 時該維度全部設 0（避免 division by zero）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.clean_timeseries import load_clean_timeseries
from src.preprocessing.paths import (
    SEQUENCES_3H_DIR,
    SEQUENCES_48H_DIR,
    ensure_processed_dirs,
)

logger = logging.getLogger(__name__)

_FEATURE_COLS = ["view_count", "like_count", "comment_count"]

# 迴歸序列額外加 log(max_view_count+1) 作為第 4 維，保留絕對尺度
_REGRESS_FEATURE_COLS = ["view_count", "like_count", "comment_count"]

CLASSIFY_WINDOW_MIN = 180.0    # 0–3h
REGRESS_WINDOW_MIN  = 2880.0   # 0–48h


def _normalize_per_window(arr: np.ndarray, append_log_max_views: bool = False) -> np.ndarray:
    """每個 column 除以該 column 最大值；最大值 0 → 全 0。
    append_log_max_views=True 時，在正規化後額外附加第 4 欄 log(max_view+1)，保留絕對尺度。"""
    out = arr.astype(np.float32, copy=True)
    raw_view_max = float(out[:, 0].max()) if out.shape[0] > 0 else 0.0
    for j in range(out.shape[1]):
        col_max = out[:, j].max() if out.shape[0] > 0 else 0.0
        if col_max > 0:
            out[:, j] = out[:, j] / col_max
        else:
            out[:, j] = 0.0
    if append_log_max_views:
        log_col = np.full((out.shape[0], 1), np.log1p(raw_view_max), dtype=np.float32)
        out = np.concatenate([out, log_col], axis=1)
    return out


def _extract_window(
    ts: pd.DataFrame,
    video_id: str,
    upper_bound_min: float,
    lower_bound_min: float = 0.0,
) -> np.ndarray | None:
    """抽出單支影片在 [lower, upper] 分鐘內的時序矩陣。"""
    g = ts[ts["video_id"] == video_id]
    g = g[(g["time_since_publish_minutes"] >= lower_bound_min) &
          (g["time_since_publish_minutes"] <= upper_bound_min)]
    g = g.sort_values("time_since_publish_minutes")
    if g.empty:
        return None
    arr = g[_FEATURE_COLS].to_numpy(dtype=np.float64)
    # NaN → 0；缺值在 clean_timeseries.py 已經做過線性插補，這裡是保險
    arr = np.nan_to_num(arr, nan=0.0)
    is_regression = upper_bound_min >= REGRESS_WINDOW_MIN
    return _normalize_per_window(arr, append_log_max_views=is_regression)


def build_sequences_3h(ts: pd.DataFrame | None = None) -> int:
    """每支影片寫一個 npy。回傳寫出的檔案數。"""
    if ts is None:
        ts = load_clean_timeseries()
    if ts.empty:
        logger.warning("clean_timeseries 空，sequences_3h 未產出")
        return 0

    ensure_processed_dirs()
    n_written = 0
    for vid in ts["video_id"].unique():
        arr = _extract_window(ts, vid, CLASSIFY_WINDOW_MIN)
        if arr is None or arr.shape[0] < 2:
            continue
        np.save(SEQUENCES_3H_DIR / f"{vid}.npy", arr)
        n_written += 1
    logger.info("sequences_3h 寫入 %d 個 npy → %s", n_written, SEQUENCES_3H_DIR)
    return n_written


def build_sequences_48h(ts: pd.DataFrame | None = None) -> int:
    """每支影片寫一個 {video_id}_first48h.npy。"""
    if ts is None:
        ts = load_clean_timeseries()
    if ts.empty:
        logger.warning("clean_timeseries 空，sequences_48h 未產出")
        return 0

    ensure_processed_dirs()
    n_written = 0
    for vid in ts["video_id"].unique():
        arr = _extract_window(ts, vid, REGRESS_WINDOW_MIN)
        if arr is None or arr.shape[0] < 3:
            continue
        sample_id = f"{vid}_first48h"
        np.save(SEQUENCES_48H_DIR / f"{sample_id}.npy", arr)
        n_written += 1
    logger.info("sequences_48h 寫入 %d 個 npy → %s", n_written, SEQUENCES_48H_DIR)
    return n_written


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ts = load_clean_timeseries()
    build_sequences_3h(ts)
    build_sequences_48h(ts)


if __name__ == "__main__":
    main()
