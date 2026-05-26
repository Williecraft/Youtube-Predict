"""
資料分割與共用工具。

temporal_split: 依 publish_time 嚴格時間序列分割 Train/Valid/Test，
                防止 Temporal Data Leakage。
"""

from __future__ import annotations

import pandas as pd


def temporal_split(
    df: pd.DataFrame,
    time_col: str = "publish_time",
    train_frac: float = 0.70,
    valid_frac: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    依 time_col 嚴格時間序列排序後分割成 train / valid / test。

    比例: train=70%, valid=15%, test=15%（最晚的資料作為 test）。
    同一 video_id 不會跨 split（因為是逐影片排序，單一影片只有一列）。
    """
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df.sort_values(time_col).reset_index(drop=True)

    n = len(df)
    n_train = int(n * train_frac)
    n_valid = int(n * valid_frac)

    train = df.iloc[:n_train].copy()
    valid = df.iloc[n_train: n_train + n_valid].copy()
    test  = df.iloc[n_train + n_valid:].copy()

    return train, valid, test
