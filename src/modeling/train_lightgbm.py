"""
LightGBM 分類模型，預測 is_viral_48h。

訓練策略：
  - K-Fold (5折) 在 train split 上產生 OOF 機率 → lgbm_oof_proba.csv (供 Stacking)
  - 再以完整 train split + early stopping on valid 訓練最終模型
  - Test 機率輸出 → lgbm_test_proba.csv (供 Stacking)

輸出：
  models/lightgbm_classifier.pkl
  results/lgbm_oof_proba.csv
  results/lgbm_test_proba.csv
  results/metrics.csv (appended)
"""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.model_selection import KFold
import lightgbm as lgb

from src.modeling.evaluate import compute_classification_metrics, find_best_threshold
from src.modeling.utils import temporal_split
from src.preprocessing.paths import (
    LABEL_DATASET_CSV,
    MODELS_DIR,
    RESULTS_DIR,
    TABULAR_FEATURES_CSV,
)

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "duration_seconds", "publish_hour", "is_shorts", "title_length", "tag_count",
    "log_subscriber_count",
    "views_1h", "views_3h", "likes_3h", "comments_3h",
    "view_delta_0h_1h", "view_delta_1h_3h",
    "view_growth_rate_1h", "views_per_minute_early",
    "like_view_ratio_3h", "comment_view_ratio_3h", "engagement_rate_early",
    "log_views_3h", "log_likes_3h", "log_comments_3h",
]
TARGET_COL = "is_viral_48h"
N_FOLDS = 5


def _safe_pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def load_data() -> pd.DataFrame:
    feats = pd.read_csv(TABULAR_FEATURES_CSV)
    labels = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id", TARGET_COL])
    df = feats.merge(labels, on="video_id", how="inner")
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

    scale_pos_weight = float((y_train == 0).sum()) / max(float((y_train == 1).sum()), 1.0)

    lgb_params = {
        "objective": "binary",
        "metric": "average_precision",
        "scale_pos_weight": scale_pos_weight,
        "num_leaves": 63,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbosity": -1,
        "random_state": 42,
        "device": "gpu",
    }

    # ── OOF 預測（在 train_df 的 K-Fold 上）──────────────────────────────
    oof_proba = np.zeros(len(train_df))
    kf = KFold(n_splits=N_FOLDS, shuffle=False)

    for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train)):
        X_tr, X_val = X_train[tr_idx], X_train[val_idx]
        y_tr, y_val = y_train[tr_idx], y_train[val_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dval   = lgb.Dataset(X_val, label=y_val, reference=dtrain)

        fold_model = lgb.train(
            lgb_params,
            dtrain,
            num_boost_round=500,
            valid_sets=[dval],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
        )
        oof_proba[val_idx] = fold_model.predict(X_val)
        logger.info("Fold %d/%d PR-AUC=%.4f", fold + 1, N_FOLDS,
                    _safe_pr_auc(y_val, oof_proba[val_idx]))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    oof_df = train_df[["video_id"]].copy().reset_index(drop=True)
    oof_df["lgbm_oof_proba"] = oof_proba
    oof_df["label"] = y_train
    oof_df.to_csv(RESULTS_DIR / "lgbm_oof_proba.csv", index=False)
    logger.info("OOF 預測儲存 → results/lgbm_oof_proba.csv")

    # ── 最終模型（完整 train + early stopping on valid）───────────────────
    dtrain_full = lgb.Dataset(X_train, label=y_train)
    dvalid      = lgb.Dataset(X_valid, label=y_valid, reference=dtrain_full)
    final_model = lgb.train(
        lgb_params,
        dtrain_full,
        num_boost_round=500,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )

    valid_prob = final_model.predict(X_valid)
    best_thr = find_best_threshold(y_valid, valid_prob)
    for split, prob, y in [
        ("valid", valid_prob, y_valid),
        ("test",  final_model.predict(X_test), y_test),
    ]:
        compute_classification_metrics(y, prob, model_name="lightgbm_classifier",
                                       split=split, threshold=best_thr)

    # Test 機率（供 Stacking）
    test_proba_df = test_df[["video_id"]].copy().reset_index(drop=True)
    test_proba_df["lgbm_test_proba"] = final_model.predict(X_test)
    test_proba_df["label"] = y_test
    test_proba_df.to_csv(RESULTS_DIR / "lgbm_test_proba.csv", index=False)
    logger.info("Test 機率儲存 → results/lgbm_test_proba.csv")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "lightgbm_classifier.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": final_model,
            "feature_cols": FEATURE_COLS,
        }, f)
    logger.info("模型儲存 → %s", model_path)


if __name__ == "__main__":
    train()
