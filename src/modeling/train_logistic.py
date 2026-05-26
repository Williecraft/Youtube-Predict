"""
Logistic Regression baseline 分類器。

輸入：
  tabular_features.csv  ← 0–3h 特徵（防洩漏）
  label_dataset.csv     ← is_viral_48h 標籤

輸出：
  models/logistic_regression.pkl
  results/metrics.csv (appended)
"""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling.evaluate import compute_classification_metrics
from src.modeling.utils import temporal_split
from src.preprocessing.paths import LABEL_DATASET_CSV, MODELS_DIR, TABULAR_FEATURES_CSV

logger = logging.getLogger(__name__)

# 嚴格限制於 0–3h 的特徵欄位（防洩漏規則）
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

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_valid_s = scaler.transform(X_valid)
    X_test_s  = scaler.transform(X_test)

    # class_weight='balanced' 處理類別不平衡
    clf = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
        solver="lbfgs",
    )
    clf.fit(X_train_s, y_train)

    for split, X_s, y in [("valid", X_valid_s, y_valid), ("test", X_test_s, y_test)]:
        prob = clf.predict_proba(X_s)[:, 1]
        compute_classification_metrics(y, prob, model_name="logistic_regression", split=split)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "logistic_regression.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": clf, "scaler": scaler, "feature_cols": FEATURE_COLS}, f)
    logger.info("模型儲存 → %s", model_path)


if __name__ == "__main__":
    train()
