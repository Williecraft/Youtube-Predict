"""
集中所有資料路徑。前處理各模組統一從這裡 import，
方便日後切換 data root（例如指向外部硬碟）。

對應 PROJECT_CONTEXT.md §1 的目錄結構。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── data roots ────────────────────────────────────────────────────────────
DATA_DIR       = REPO_ROOT / "data"
RAW_DIR        = DATA_DIR / "raw"
PROCESSED_DIR  = DATA_DIR / "processed"

STATIC_DIR     = RAW_DIR / "static"
TIMESERIES_DIR = RAW_DIR / "timeseries" / "by_video"
COMMENTS_DIR   = RAW_DIR / "comments" / "by_video"

# ── raw input files ──────────────────────────────────────────────────────
VIDEOS_STATIC_JSON  = STATIC_DIR / "videos_static.json"
CHANNEL_STATIC_JSON = STATIC_DIR / "channel_static.json"
STATE_DB            = DATA_DIR / "state.db"

# ── processed output files (PROJECT_CONTEXT.md §12) ──────────────────────
LABEL_DATASET_CSV          = PROCESSED_DIR / "label_dataset.csv"
TABULAR_FEATURES_CSV       = PROCESSED_DIR / "tabular_features.csv"
REGRESSION_DATASET_CSV     = PROCESSED_DIR / "regression_dataset.csv"
REGRESSION_FEATURES_CSV    = PROCESSED_DIR / "regression_features_48h.csv"
CLEAN_TIMESERIES_PARQUET   = PROCESSED_DIR / "clean_timeseries.parquet"  # §3 中間產物

SEQUENCES_3H_DIR  = PROCESSED_DIR / "sequences_3h"
SEQUENCES_48H_DIR = PROCESSED_DIR / "sequences_48h"

# ── result dirs ──────────────────────────────────────────────────────────
RESULTS_DIR = REPO_ROOT / "results"
MODELS_DIR  = REPO_ROOT / "models"


def ensure_processed_dirs() -> None:
    """確保前處理會用到的輸出目錄都存在。"""
    for d in (PROCESSED_DIR, SEQUENCES_3H_DIR, SEQUENCES_48H_DIR,
              RESULTS_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
