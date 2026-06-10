"""
Logistic Regression baseline 分類器。

用法：
  python -m src.modeling.train_logistic                  # 預設 Group B
  python -m src.modeling.train_logistic --feature-group A
  python -m src.modeling.train_logistic --feature-group C1
"""

from __future__ import annotations

import argparse
import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling.evaluate import compute_classification_metrics
from src.modeling.utils import apply_split
from src.preprocessing.paths import (
    COMMENT_FEATURES_CSV,
    LABEL_DATASET_CSV,
    MODELS_DIR,
    TABULAR_FEATURES_CSV,
)

logger = logging.getLogger(__name__)

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


def load_data(feature_group: str) -> pd.DataFrame:
    feature_cols = FEATURE_GROUPS[feature_group]
    feats = pd.read_csv(TABULAR_FEATURES_CSV)
    labels = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id", TARGET_COL])
    df = feats.merge(labels, on="video_id", how="inner")
    if feature_group in ("C1", "C2", "C3"):
        if not COMMENT_FEATURES_CSV.exists():
            raise FileNotFoundError("comment_features.csv 不存在，請先跑 build_comment_emotion_features.py")
        cmt = pd.read_csv(COMMENT_FEATURES_CSV)
        df = df.merge(cmt, on="video_id", how="left")
    df["is_shorts"] = df["is_shorts"].astype(int)
    keep = ["video_id", "publish_time", TARGET_COL] + feature_cols
    return df[[c for c in keep if c in df.columns]]


def train(feature_group: str = "B") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    feature_cols = FEATURE_GROUPS[feature_group]
    logger.info("Logistic Regression  feature_group=%s", feature_group)

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

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_valid_s = scaler.transform(X_valid)
    X_test_s  = scaler.transform(X_test)

    clf = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
        solver="lbfgs",
    )
    clf.fit(X_train_s, y_train)

    for split, X_s, y in [("valid", X_valid_s, y_valid), ("test", X_test_s, y_test)]:
        prob = clf.predict_proba(X_s)[:, 1]
        compute_classification_metrics(
            y, prob,
            model_name="logistic_regression",
            split=split,
            feature_group=feature_group,
        )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"logistic_regression_{feature_group}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": clf, "scaler": scaler, "feature_cols": feature_cols,
                     "feature_group": feature_group}, f)
    if feature_group == "B":
        with open(MODELS_DIR / "logistic_regression.pkl", "wb") as f:
            pickle.dump({"model": clf, "scaler": scaler, "feature_cols": feature_cols}, f)
    logger.info("模型儲存 → %s", model_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-group", default="B",
                        choices=list(FEATURE_GROUPS.keys()))
    args = parser.parse_args()
    train(feature_group=args.feature_group)


if __name__ == "__main__":
    main()
