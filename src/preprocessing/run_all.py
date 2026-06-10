"""
前處理主入口：把爬蟲產出的 raw 資料一次轉成所有 processed 檔案。

使用：
    python -m src.preprocessing.run_all
    python -m src.preprocessing.run_all --skip sequences   # 跳過某步驟
    python -m src.preprocessing.run_all --only labels      # 只跑某步驟

輸出（PROJECT_CONTEXT.md §3 step 11）：
    data/processed/label_dataset.csv
    data/processed/tabular_features.csv
    data/processed/regression_dataset.csv
    data/processed/regression_features_48h.csv
    data/processed/clean_timeseries.parquet      (中間產物)
    data/processed/sequences_3h/{video_id}.npy
    data/processed/sequences_48h/{sample_id}.npy

包含步驟：
    clean_timeseries → labels → split → tabular_features → sequences → regression

    Comment emotion features 由 build_comment_emotion_features.py 單獨跑（需要 GPU），
    不納入主 pipeline，避免拖慢一般 preprocessing。

每個 step 為獨立 callable，可單獨匯入或跑 module main()。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable

from src.preprocessing import (
    build_labels,
    build_regression_dataset,
    build_sequences,
    build_tabular_features,
    clean_timeseries,
    split_dataset,
)
from src.preprocessing.paths import ensure_processed_dirs

logger = logging.getLogger("preprocessing.run_all")


# (step_name, callable) — 順序很重要：下游 step 依賴上游輸出檔
STEPS: list[tuple[str, Callable[[], None]]] = [
    ("clean_timeseries",  clean_timeseries.main),
    ("labels",            build_labels.main),
    ("split",             split_dataset.main),       # 分組時序切分（在 labels 之後）
    ("tabular_features",  build_tabular_features.main),
    ("sequences",         build_sequences.main),
    ("regression",        build_regression_dataset.main),
]


def run(only: str | None = None, skip: set[str] | None = None) -> None:
    ensure_processed_dirs()
    skip = skip or set()

    for name, fn in STEPS:
        if only and name != only:
            continue
        if name in skip:
            logger.info("skip step=%s", name)
            continue
        t0 = time.monotonic()
        logger.info("─── step=%s 開始 ───", name)
        try:
            fn()
        except Exception:
            logger.exception("step=%s 失敗", name)
            raise
        logger.info("─── step=%s 完成（%.1fs）───", name, time.monotonic() - t0)


def main():
    parser = argparse.ArgumentParser(description="YouTube Predict — 前處理 pipeline")
    parser.add_argument("--only", help="只跑指定 step")
    parser.add_argument("--skip", nargs="*", default=[], help="跳過指定 step（可多個）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    run(only=args.only, skip=set(args.skip))


if __name__ == "__main__":
    main()
