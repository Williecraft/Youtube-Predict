"""
LightGBM 分類模型，預測 is_viral_48h。

訓練策略：
  - K-Fold (5折) 在 train split 上產生 OOF 機率 → lgbm_oof_proba_{group}.csv
  - 再以完整 train split + early stopping on valid 訓練最終模型
  - Test 機率輸出 → lgbm_test_proba_{group}.csv

用法：
  python -m src.modeling.train_lightgbm                  # 預設 Group B
  python -m src.modeling.train_lightgbm --feature-group A
  python -m src.modeling.train_lightgbm --feature-group C1
"""

from __future__ import annotations

import argparse
import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.model_selection import KFold
import lightgbm as lgb

from src.modeling.evaluate import compute_classification_metrics, find_best_threshold
from src.modeling.utils import apply_split
from src.preprocessing.paths import (
    COMMENT_FEATURES_CSV,
    LABEL_DATASET_CSV,
    MODELS_DIR,
    RESULTS_DIR,
    TABULAR_FEATURES_CSV,
)

logger = logging.getLogger(__name__)

# ── Feature Groups ─────────────────────────────────────────────────────────
_FEAT_A = [
    "duration_seconds", "publish_hour", "is_shorts", "title_length", "tag_count",
    "log_subscriber_count",
]
_FEAT_B = _FEAT_A + [
    "views_1h", "views_3h", "likes_3h", "comments_3h",
    "view_delta_0h_1h", "view_delta_1h_3h",
    "view_growth_rate_1h", "views_per_minute_early",
    "like_view_ratio_3h", "comment_view_ratio_3h", "engagement_rate_early",
    "log_views_3h", "log_likes_3h", "log_comments_3h",
]
_FEAT_C1_EXTRA = ["comment_sentiment_score", "top_comment_like_ratio", "comment_count_3h"]
_FEAT_C2_EXTRA = [
    "comment_valence_mean", "comment_valence_std",
    "comment_arousal_mean", "comment_arousal_std", "comment_high_arousal_ratio",
]

FEATURE_GROUPS: dict[str, list[str]] = {
    "A":  _FEAT_A,
    "B":  _FEAT_B,
    "C1": _FEAT_B + _FEAT_C1_EXTRA,
    "C2": _FEAT_B + _FEAT_C2_EXTRA,
    "C3": _FEAT_B + _FEAT_C1_EXTRA + _FEAT_C2_EXTRA,
}

TARGET_COL = "is_viral_48h"
N_FOLDS = 5


def _safe_pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def load_data(feature_group: str) -> pd.DataFrame:
    feature_cols = FEATURE_GROUPS[feature_group]
    feats = pd.read_csv(TABULAR_FEATURES_CSV)
    labels = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id", TARGET_COL])
    df = feats.merge(labels, on="video_id", how="inner")

    if feature_group in ("C1", "C2", "C3"):
        if not COMMENT_FEATURES_CSV.exists():
            raise FileNotFoundError(
                f"comment_features.csv 不存在，請先執行 build_comment_emotion_features.py "
                f"（feature_group={feature_group} 需要留言情緒特徵）"
            )
        cmt = pd.read_csv(COMMENT_FEATURES_CSV)
        df = df.merge(cmt, on="video_id", how="left")

    df["is_shorts"] = df["is_shorts"].astype(int)
    # 只保留需要的欄位（避免洩漏）
    keep = ["video_id", "publish_time", TARGET_COL] + feature_cols
    keep = [c for c in keep if c in df.columns]
    return df[keep]


def train(feature_group: str = "B") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    feature_cols = FEATURE_GROUPS[feature_group]
    logger.info("LightGBM 分類  feature_group=%s  n_features=%d", feature_group, len(feature_cols))

    df = load_data(feature_group)
    if df.empty:
        logger.warning("資料為空，終止訓練")
        return

    train_df, valid_df, test_df = apply_split(df)
    logger.info("Split: train=%d, valid=%d, test=%d", len(train_df), len(valid_df), len(test_df))

    X_train = train_df[feature_cols].fillna(0).values
    y_train = train_df[TARGET_COL].values
    X_valid = valid_df[feature_cols].fillna(0).values
    y_valid = valid_df[TARGET_COL].values
    X_test  = test_df[feature_cols].fillna(0).values
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
    oof_path = RESULTS_DIR / f"lgbm_oof_proba_{feature_group}.csv"
    oof_df.to_csv(oof_path, index=False)
    # Group B 也寫一份無後綴版本供 stacking 使用
    if feature_group == "B":
        oof_df.to_csv(RESULTS_DIR / "lgbm_oof_proba.csv", index=False)
    logger.info("OOF 預測儲存 → %s", oof_path)

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
        compute_classification_metrics(
            y, prob,
            model_name="lightgbm_classifier",
            split=split,
            threshold=best_thr,
            feature_group=feature_group,
        )

    # Test 機率（供 Stacking）
    test_proba_df = test_df[["video_id"]].copy().reset_index(drop=True)
    test_proba_df["lgbm_test_proba"] = final_model.predict(X_test)
    test_proba_df["label"] = y_test
    test_path = RESULTS_DIR / f"lgbm_test_proba_{feature_group}.csv"
    test_proba_df.to_csv(test_path, index=False)
    if feature_group == "B":
        test_proba_df.to_csv(RESULTS_DIR / "lgbm_test_proba.csv", index=False)
    logger.info("Test 機率儲存 → %s", test_path)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"lightgbm_classifier_{feature_group}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": final_model,
            "feature_cols": feature_cols,
            "feature_group": feature_group,
        }, f)
    if feature_group == "B":
        with open(MODELS_DIR / "lightgbm_classifier.pkl", "wb") as f:
            pickle.dump({"model": final_model, "feature_cols": feature_cols}, f)
    logger.info("模型儲存 → %s", model_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-group", default="B",
                        choices=list(FEATURE_GROUPS.keys()),
                        help="Feature group to use (default: B)")
    args = parser.parse_args()
    train(feature_group=args.feature_group)


if __name__ == "__main__":
    main()
