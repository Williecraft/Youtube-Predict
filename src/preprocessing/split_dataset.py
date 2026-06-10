"""
分組時序切分（Stratified Temporal Split）。

問題：若直接把所有影片按 publish_time 排序後切 70/15/15，
    Shorts（最近才大量爬）會全落入 test，train 幾乎只有長影片，
    導致模型在長影片上訓練、在 Shorts 上評估，結果失去意義。

解決：Shorts 與長影片各自按 publish_time 排序，分別切 70/15/15，再合併。
    組內仍保持時序方向（舊→新），同類影片的 test 仍是最新的，
    但兩類各自佔 ~30%/~70% 的比例在每個 split 均維持。

輸出：
    data/split/split_map.csv  — video_id, split (train/valid/test)
    data/split/train.csv      — 只含 video_id
    data/split/valid.csv
    data/split/test.csv
"""

from __future__ import annotations

import logging

import pandas as pd

from src.preprocessing.load_raw import load_videos_static
from src.preprocessing.paths import (
    LABEL_DATASET_CSV,
    REGRESSION_DATASET_CSV,
    SPLIT_DIR,
    SPLIT_MAP_CSV,
    ensure_processed_dirs,
)

logger = logging.getLogger(__name__)


def stratified_temporal_split(
    df: pd.DataFrame,
    publish_col: str = "publish_time",
    group_col: str = "is_shorts",
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> pd.DataFrame:
    """
    Shorts 與長影片各自按 publish_time 時序排序，分別切 70/15/15，再合併。

    Parameters
    ----------
    df : DataFrame，至少含 video_id, publish_col, group_col
    publish_col : 發布時間欄位
    group_col   : 分組欄位（True = Shorts, False = Long）
    ratios      : (train, valid, test) 比例，需加總為 1

    Returns
    -------
    DataFrame with columns [video_id, split]
    """
    df = df.copy()
    df[publish_col] = pd.to_datetime(df[publish_col], utc=True, errors="coerce")
    df = df.dropna(subset=[publish_col, group_col])
    df[group_col] = df[group_col].astype(bool)

    result: list[pd.DataFrame] = []
    for group_val, grp in df.groupby(group_col, sort=False):
        grp = grp.sort_values(publish_col).reset_index(drop=True)
        n = len(grp)
        n_tr = int(n * ratios[0])
        n_va = int(n * ratios[1])

        split_labels = ["test"] * n
        for i in range(n_tr):
            split_labels[i] = "train"
        for i in range(n_tr, n_tr + n_va):
            split_labels[i] = "valid"

        grp = grp.copy()
        grp["split"] = split_labels
        label = "Shorts" if group_val else "Long"
        logger.info(
            "  [%s] n=%d  train=%d  valid=%d  test=%d",
            label, n, n_tr, n_va, n - n_tr - n_va,
        )
        result.append(grp[["video_id", "split"]])

    return pd.concat(result, ignore_index=True)


def build_split_map() -> pd.DataFrame:
    """
    以 label_dataset.csv 為主，取得 video_id / publish_time / is_shorts，
    做分組時序切分。回歸任務中沒有出現在 label_dataset 的 video_id，
    後續由 apply_split() fallback 處理。

    回傳 DataFrame [video_id, split]。
    """
    if not LABEL_DATASET_CSV.exists():
        raise RuntimeError("找不到 label_dataset.csv，請先跑 build_labels.py")

    needed_cols = ["video_id", "publish_time", "is_shorts"]
    clf_df = pd.read_csv(LABEL_DATASET_CSV, usecols=needed_cols)
    needed = clf_df.dropna(subset=["publish_time", "is_shorts"])

    # 補充回歸任務中存在、但分類沒有的 video_id（從 static 補 is_shorts）
    if REGRESSION_DATASET_CSV.exists():
        reg_ids = set(pd.read_csv(REGRESSION_DATASET_CSV,
                                  usecols=["video_id"])["video_id"])
        clf_ids = set(needed["video_id"])
        extra_ids = reg_ids - clf_ids
        if extra_ids:
            static = load_videos_static()
            extra = static[static["video_id"].isin(extra_ids)][needed_cols].dropna()
            needed = pd.concat([needed, extra], ignore_index=True)
            logger.info("補充 %d 部僅出現在回歸任務的影片", len(extra))

    n_before = len(needed)
    logger.info("split 輸入 %d 部影片", n_before)

    split_map = stratified_temporal_split(needed)

    # 統計
    for sp in ["train", "valid", "test"]:
        sub = split_map[split_map["split"] == sp]
        shorts_ids = set(needed.loc[needed["is_shorts"] == True, "video_id"])
        s = sub["video_id"].isin(shorts_ids).sum()
        logger.info("  %-5s: %4d  Shorts=%d (%.0f%%)",
                    sp, len(sub), s, 100 * s / len(sub) if sub.shape[0] else 0)

    return split_map


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_processed_dirs()
    split_map = build_split_map()

    SPLIT_MAP_CSV.parent.mkdir(parents=True, exist_ok=True)
    split_map.to_csv(SPLIT_MAP_CSV, index=False)
    logger.info("split_map 寫入 %s（%d 部影片）", SPLIT_MAP_CSV, len(split_map))

    for sp in ["train", "valid", "test"]:
        path = SPLIT_DIR / f"{sp}.csv"
        split_map[split_map["split"] == sp][["video_id"]].to_csv(path, index=False)
        logger.info("  %s → %s", sp, path)


if __name__ == "__main__":
    main()
