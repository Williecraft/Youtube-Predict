"""
SHAP 特徵重要性分析（基於 LightGBM 分類模型）。

輸入：
  models/lightgbm_classifier.pkl
  data/processed/tabular_features.csv
  data/processed/label_dataset.csv

輸出：
  results/feature_importance_shap.csv
    欄位: feature, mean_abs_shap (test split 平均絕對 SHAP 值)
"""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
import shap

from src.modeling.utils import temporal_split
from src.preprocessing.paths import (
    LABEL_DATASET_CSV,
    MODELS_DIR,
    RESULTS_DIR,
    TABULAR_FEATURES_CSV,
)

logger = logging.getLogger(__name__)


def run_shap_analysis() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    model_path = MODELS_DIR / "lightgbm_classifier.pkl"
    if not model_path.exists():
        raise FileNotFoundError(
            f"找不到模型檔 {model_path}，請先執行 train_lightgbm.py"
        )

    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    lgbm_model = bundle["model"]
    feature_cols = bundle["feature_cols"]

    # 載入資料，取 test split
    feats = pd.read_csv(TABULAR_FEATURES_CSV)
    labels = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id", "is_viral_48h"])
    df = feats.merge(labels, on="video_id", how="inner")
    df["is_shorts"] = df["is_shorts"].astype(int)

    _, _, test_df = temporal_split(df)
    X_test = test_df[feature_cols].fillna(0).values

    logger.info("計算 SHAP values（test set size=%d）...", len(test_df))
    explainer = shap.TreeExplainer(lgbm_model)
    shap_values = explainer.shap_values(X_test)

    # shap_values 可能是 list (binary: index 1 為正類) 或 ndarray
    if isinstance(shap_values, list):
        sv = shap_values[1]
    else:
        sv = shap_values

    mean_abs_shap = np.abs(sv).mean(axis=0)
    importance_df = pd.DataFrame({
        "feature": feature_cols,
        "mean_abs_shap": mean_abs_shap,
    }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "feature_importance_shap.csv"
    importance_df.to_csv(out_path, index=False)
    logger.info("SHAP 特徵重要性儲存 → %s", out_path)

    # 印出 top-10
    logger.info("Top-10 features:\n%s", importance_df.head(10).to_string(index=False))


if __name__ == "__main__":
    run_shap_analysis()
