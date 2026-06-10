"""
LightGBM 迴歸模型，預測 log_next_24h_views。

用法：
  python -m src.modeling.train_regression                  # 預設 Group B
  python -m src.modeling.train_regression --feature-group C1
"""

from __future__ import annotations

import argparse
import logging
import pickle

import numpy as np
import pandas as pd
import lightgbm as lgb

from src.modeling.evaluate import compute_regression_metrics
from src.modeling.utils import apply_split
from src.preprocessing.paths import (
    COMMENT_FEATURES_CSV,
    MODELS_DIR,
    REGRESSION_DATASET_CSV,
    REGRESSION_FEATURES_CSV,
    RESULTS_DIR,
)

logger = logging.getLogger(__name__)

_FEAT_B = [
    "duration_seconds", "publish_hour", "is_shorts", "title_length", "tag_count",
    "log_subscriber_count",
    "views_1h", "views_3h", "views_24h", "views_48h",
    "log_views_1h", "log_views_3h", "log_views_24h", "log_views_48h",
    "growth_1h_to_3h", "growth_3h_to_24h", "growth_24h_to_48h",
    "rate_late_to_early",
    "likes_48h", "comments_48h",
    "like_view_ratio_48h", "comment_view_ratio_48h", "engagement_rate_48h",
]
_FEAT_C1_EXTRA = ["comment_sentiment_score", "top_comment_like_ratio", "comment_count_3h"]
_FEAT_C2_EXTRA = [
    "comment_valence_mean", "comment_valence_std",
    "comment_arousal_mean", "comment_arousal_std", "comment_high_arousal_ratio",
]

FEATURE_GROUPS: dict[str, list[str]] = {
    "B":  _FEAT_B,
    "C1": _FEAT_B + _FEAT_C1_EXTRA,
    "C2": _FEAT_B + _FEAT_C2_EXTRA,
    "C3": _FEAT_B + _FEAT_C1_EXTRA + _FEAT_C2_EXTRA,
}

TARGET_COL = "log_next_24h_views"


def load_data(feature_group: str) -> pd.DataFrame:
    feature_cols = FEATURE_GROUPS[feature_group]
    feats = pd.read_csv(REGRESSION_FEATURES_CSV)
    targets = pd.read_csv(REGRESSION_DATASET_CSV,
                          usecols=["sample_id", "video_id", TARGET_COL, "publish_time"])
    df = feats.merge(targets, on=["sample_id"], how="inner", suffixes=("", "_tgt"))
    if "publish_time_tgt" in df.columns:
        df = df.drop(columns=["publish_time_tgt"])
    if "video_id_tgt" in df.columns:
        df = df.drop(columns=["video_id_tgt"])

    if feature_group in ("C1", "C2", "C3"):
        if not COMMENT_FEATURES_CSV.exists():
            raise FileNotFoundError("comment_features.csv 不存在，請先跑 build_comment_emotion_features.py")
        cmt = pd.read_csv(COMMENT_FEATURES_CSV)
        df = df.merge(cmt, on="video_id", how="left")

    df["is_shorts"] = df["is_shorts"].astype(int)
    keep = ["sample_id", "video_id", "publish_time", TARGET_COL] + feature_cols
    return df[[c for c in keep if c in df.columns]]


def train(feature_group: str = "B") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    feature_cols = FEATURE_GROUPS[feature_group]
    logger.info("LightGBM 迴歸  feature_group=%s  n_features=%d", feature_group, len(feature_cols))

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
        compute_regression_metrics(
            y, pred,
            model_name="lightgbm_regressor",
            split=split,
            feature_group=feature_group,
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    test_pred_df = test_df[["sample_id", "video_id"]].copy().reset_index(drop=True)
    test_pred_df["lgbm_reg_pred"] = model.predict(X_test)
    test_pred_df["label"] = y_test
    pred_path = RESULTS_DIR / f"lgbm_reg_test_pred_{feature_group}.csv"
    test_pred_df.to_csv(pred_path, index=False)
    if feature_group == "B":
        test_pred_df.to_csv(RESULTS_DIR / "lgbm_reg_test_pred.csv", index=False)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"lightgbm_regressor_{feature_group}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": feature_cols,
                     "feature_group": feature_group}, f)
    if feature_group == "B":
        with open(MODELS_DIR / "lightgbm_regressor.pkl", "wb") as f:
            pickle.dump({"model": model, "feature_cols": feature_cols}, f)
    logger.info("模型儲存 → %s", model_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-group", default="B",
                        choices=list(FEATURE_GROUPS.keys()))
    args = parser.parse_args()
    train(feature_group=args.feature_group)


if __name__ == "__main__":
    main()
