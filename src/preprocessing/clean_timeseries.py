"""
時序資料清理。對應 PROJECT_CONTEXT.md §3 step 2/3/4/5/6。

輸入：load_raw.load_timeseries() + load_raw.load_videos_static()
輸出：data/processed/clean_timeseries.parquet（中間產物，下游模組讀取）

步驟：
 1. 所有 crawl_time 轉成 UTC tz-aware datetime
 2. 補/校正 time_since_publish_minutes（用 static.publish_time 為準）
 3. 過濾 video_status — 只保留 OK / 空字串（爬蟲實際輸出 OK / UNKNOWN，不是 'public'）
 4. 去重：同 (video_id, time_since_publish_minutes 四捨五入到分鐘) 取最新一筆
 5. 數值欄位轉 int/float，缺值保留 NaN
 6. 在 0–3h 內缺值做線性插補（PROJECT_CONTEXT.md §3 step 6「少量缺值線性插補」）

注意：時序原始檔是 append-only，重啟爬蟲可能寫入重複 snapshot；本步驟負責去重。
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.preprocessing.load_raw import load_timeseries, load_videos_static
from src.preprocessing.paths import CLEAN_TIMESERIES_PARQUET, ensure_processed_dirs

logger = logging.getLogger(__name__)

# video_status 視為「公開可分析」的值。爬蟲實際輸出 OK；其他狀態（UNPLAYABLE,
# LOGIN_REQUIRED, AGE_VERIFICATION_REQUIRED, UNKNOWN 等）一律排除。
_PUBLIC_STATUSES = {"OK", "ok"}

# 線性插補只在 0–3h 窗口內做（早期資料對分類最關鍵）
_INTERP_WINDOW_MIN = 0
_INTERP_WINDOW_MAX = 180  # 3h


def clean_timeseries(
    ts: pd.DataFrame | None = None,
    static: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """主清理函式。傳入 None 則自行 load_raw。"""
    if ts is None:
        ts = load_timeseries()
    if static is None:
        static = load_videos_static()

    if ts.empty:
        logger.warning("timeseries 為空，clean_timeseries 直接回傳空 DataFrame")
        return ts

    ts = ts.copy()

    # 1. crawl_time → UTC datetime
    ts["crawl_time"] = pd.to_datetime(ts["crawl_time"], utc=True, errors="coerce")
    ts = ts[ts["crawl_time"].notna()]

    # 2. 用 static.publish_time 重新計算 time_since_publish_minutes
    pub = static[["video_id", "publish_time"]].copy()
    pub["publish_time"] = pd.to_datetime(pub["publish_time"], utc=True, errors="coerce")
    ts = ts.merge(pub, on="video_id", how="left")
    ts["time_since_publish_minutes"] = (
        (ts["crawl_time"] - ts["publish_time"]).dt.total_seconds() / 60.0
    ).round(1)
    # 缺 publish_time 的影片無法對齊時間軸 → 排除
    ts = ts[ts["publish_time"].notna() & ts["time_since_publish_minutes"].notna()]

    # 3. 過濾 video_status（保留 OK，允許空字串以涵蓋舊資料）
    status_ok = ts["video_status"].isin(_PUBLIC_STATUSES) | ts["video_status"].isna() | (ts["video_status"] == "")
    n_dropped = (~status_ok).sum()
    if n_dropped:
        logger.info("依 video_status 過濾掉 %d 筆 snapshot", n_dropped)
    ts = ts[status_ok]

    # 4. 數值欄位轉型
    for col in ("view_count", "like_count", "comment_count", "subscriber_count"):
        ts[col] = pd.to_numeric(ts[col], errors="coerce")

    # 5. 去重：(video_id, 分鐘) 同組只保留 view_count 最大的（單調遞增假設）
    ts["_t_min"] = ts["time_since_publish_minutes"].round().astype("Int64")
    ts = (
        ts.sort_values(["video_id", "_t_min", "view_count"], na_position="first")
          .drop_duplicates(["video_id", "_t_min"], keep="last")
          .drop(columns="_t_min")
          .reset_index(drop=True)
    )

    # 6. 0–3h 內缺值線性插補（按 video_id 分組、按時間排序）
    ts = ts.sort_values(["video_id", "time_since_publish_minutes"]).reset_index(drop=True)
    interp_cols = ["view_count", "like_count", "comment_count", "subscriber_count"]
    ts[interp_cols] = (
        ts.groupby("video_id", group_keys=False)
          .apply(lambda g: _interp_early(g, interp_cols))[interp_cols]
    )

    return ts


def _interp_early(group: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """在 0–3h 內做線性插補，3h 之後保留 NaN。"""
    g = group.copy()
    early_mask = g["time_since_publish_minutes"].between(_INTERP_WINDOW_MIN, _INTERP_WINDOW_MAX)
    if early_mask.sum() < 2:
        return g
    g.loc[early_mask, cols] = (
        g.loc[early_mask, cols].interpolate(method="linear", limit_direction="both")
    )
    return g


def save_clean_timeseries(df: pd.DataFrame) -> None:
    ensure_processed_dirs()
    # parquet 比 csv 小、保留 dtype；如果環境沒 pyarrow 就 fallback 到 csv
    try:
        df.to_parquet(CLEAN_TIMESERIES_PARQUET, index=False)
        logger.info("clean_timeseries 寫入 %s（%d 列）", CLEAN_TIMESERIES_PARQUET, len(df))
    except Exception as e:
        fallback = CLEAN_TIMESERIES_PARQUET.with_suffix(".csv")
        logger.warning("parquet 寫入失敗（%s），改寫 CSV：%s", e, fallback)
        df.to_csv(fallback, index=False)


def load_clean_timeseries() -> pd.DataFrame:
    """下游模組使用：讀回已清理的時序資料。"""
    if CLEAN_TIMESERIES_PARQUET.exists():
        return pd.read_parquet(CLEAN_TIMESERIES_PARQUET)
    fallback = CLEAN_TIMESERIES_PARQUET.with_suffix(".csv")
    if fallback.exists():
        return pd.read_csv(fallback, parse_dates=["crawl_time", "publish_time"])
    logger.warning("找不到 clean_timeseries 輸出；先跑 clean_timeseries.main()")
    return pd.DataFrame()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    df = clean_timeseries()
    save_clean_timeseries(df)


if __name__ == "__main__":
    main()
