"""
資料分割與共用工具。

apply_split   : 從 data/split/split_map.csv 讀取分組時序切分結果，
                依 video_id 對齊後回傳 train/valid/test。
temporal_split: 舊版純時序切分，保留供緊急 fallback。
"""

from __future__ import annotations

import logging

import pandas as pd

from src.preprocessing.paths import SPLIT_MAP_CSV

logger = logging.getLogger(__name__)


def apply_split(
    df: pd.DataFrame,
    id_col: str = "video_id",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    從 data/split/split_map.csv 讀取預先計算的分組時序切分，
    依 id_col 對齊 df，回傳 (train, valid, test)。

    split_map.csv 由 src/preprocessing/split_dataset.py 產生，
    確保 Shorts 與長影片在每個 split 中比例均衡。

    若 split_map.csv 不存在，自動 fallback 至 temporal_split()。
    """
    if not SPLIT_MAP_CSV.exists():
        logger.warning("split_map.csv 不存在，fallback 至 temporal_split()")
        return temporal_split(df, id_col=id_col)

    split_map = pd.read_csv(SPLIT_MAP_CSV, usecols=["video_id", "split"])

    # 對齊（只保留 split_map 有的 video_id）
    merged = df.merge(split_map.rename(columns={"video_id": id_col}), on=id_col, how="left")
    unmapped = merged["split"].isna().sum()
    if unmapped > 0:
        logger.warning("%d 筆 %s 不在 split_map，將被排除", unmapped, id_col)
    merged = merged.dropna(subset=["split"])

    train = merged[merged["split"] == "train"].drop(columns="split").reset_index(drop=True)
    valid = merged[merged["split"] == "valid"].drop(columns="split").reset_index(drop=True)
    test  = merged[merged["split"] == "test"].drop(columns="split").reset_index(drop=True)

    logger.info("Split (from split_map): train=%d, valid=%d, test=%d",
                len(train), len(valid), len(test))
    return train, valid, test


def temporal_split(
    df: pd.DataFrame,
    time_col: str = "publish_time",
    id_col: str = "video_id",
    train_frac: float = 0.70,
    valid_frac: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    純時序 fallback：依 time_col 排序後切 70/15/15。
    正式訓練請使用 apply_split()。
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
