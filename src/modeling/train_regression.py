"""
LightGBM 迴歸模型，預測 log_next_24h_views。

輸入：
  data/processed/regression_features_48h.csv  ← 0–48h 特徵（防洩漏）
  data/processed/regression_dataset.csv       ← log_next_24h_views 目標

防洩漏規則：
  - 目標欄位 (log_next_24h_views / next_24h_views / views_72h) 嚴格排除於輸入特徵外
  - 以 publish_time 進行 Temporal Split

輸出：
  models/lightgbm_regressor.pkl
  results/regression_metrics.csv (appended)
"""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
import lightgbm as lgb

from src.modeling.evaluate import compute_regression_metrics
from src.modeling.utils import temporal_split
from src.preprocessing.paths import (
    MODELS_DIR,
    REGRESSION_DATASET_CSV,
    REGRESSION_FEATURES_CSV,
    RESULTS_DIR,
)

logger = logging.getLogger(__name__)

# 0–48h 範圍特徵（排除任何 72h 或目標欄位）
FEATURE_COLS = [
    "duration_seconds", "publish_hour", "is_shorts", "title_length", "tag_count",
    "log_subscriber_count",
    "views_1h", "views_3h", "views_24h", "views_48h",
    "log_views_1h", "log_views_3h", "log_views_24h", "log_views_48h",
    "growth_1h_to_3h", "growth_3h_to_24h", "growth_24h_to_48h",
    "rate_late_to_early",
    "likes_48h", "comments_48h",
    "like_view_ratio_48h", "comment_view_ratio_48h", "engagement_rate_48h",
]
TARGET_COL = "log_next_24h_views"


def load_data() -> pd.DataFrame:
    feats = pd.read_csv(REGRESSION_FEATURES_CSV)
    targets = pd.read_csv(REGRESSION_DATASET_CSV, usecols=["sample_id", TARGET_COL, "publish_time"])
    df = feats.merge(targets, on=["sample_id"], how="inner", suffixes=("", "_tgt"))
    # publish_time 以 features 側為主
    if "publish_time_tgt" in df.columns:
        df = df.drop(columns=["publish_time_tgt"])
    df["is_shorts"] = df["is_shorts"].astype(int)
    return df


def train() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    df = load_data()
    if df.empty:
        logger.warning("資料為空，終止訓練")
        return

    train_df, valid_df, test_df = temporal_split(df)
    logger.info("Split: train=%d, valid=%d, test=%d", len(train_df), len(valid_df), len(test_df))

    X_train = train_df[FEATURE_COLS].fillna(0).values
    y_train = train_df[TARGET_COL].values
    X_valid = valid_df[FEATURE_COLS].fillna(0).values
    y_valid = valid_df[TARGET_COL].values
    X_test  = test_df[FEATURE_COLS].fillna(0).values
    y_test  = test_df[TARGET_COL].values

    lgb_params = {
        "objective": "regression",
        "metric": "rmse",
        "num_leaves": 63,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbosity": -1,
        "random_state": 42,
        "device": "gpu",
    }

    dtrain = lgb.Dataset(X_train, label=y_train)
    dvalid = lgb.Dataset(X_valid, label=y_valid, reference=dtrain)

    model = lgb.train(
        lgb_params,
        dtrain,
        num_boost_round=500,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )

    for split, X_s, y in [("valid", X_valid, y_valid), ("test", X_test, y_test)]:
        pred = model.predict(X_s)
        compute_regression_metrics(y, pred, model_name="lightgbm_regressor", split=split)

    # 儲存 OOF-like test predictions for LSTM regression stacking (if needed later)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    test_pred_df = test_df[["sample_id", "video_id"]].copy().reset_index(drop=True)
    test_pred_df["lgbm_reg_pred"] = model.predict(X_test)
    test_pred_df["label"] = y_test
    test_pred_df.to_csv(RESULTS_DIR / "lgbm_reg_test_pred.csv", index=False)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "lightgbm_regressor.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": FEATURE_COLS}, f)
    logger.info("模型儲存 → %s", model_path)


if __name__ == "__main__":
    train()
