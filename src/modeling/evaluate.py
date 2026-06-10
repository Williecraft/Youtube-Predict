"""
模型評估指標計算工具。

- compute_classification_metrics: F1, AUC-ROC, Precision, Recall, PR-AUC → results/metrics.csv
- compute_regression_metrics:     MAE, RMSE, RMSLE, R2               → results/regression_metrics.csv
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)

from src.preprocessing.paths import RESULTS_DIR

logger = logging.getLogger(__name__)

METRICS_CSV = RESULTS_DIR / "metrics.csv"
REGRESSION_METRICS_CSV = RESULTS_DIR / "regression_metrics.csv"


def find_best_threshold(y_true: np.ndarray, y_proba: np.ndarray) -> float:
    """在 validation set 上用 F1 最大化找最佳 threshold。"""
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, y_proba)
    f1s = np.where((precision + recall) == 0, 0,
                   2 * precision * recall / (precision + recall + 1e-9))
    best_idx = int(np.argmax(f1s[:-1]))  # thresholds 比 p/r 少一個
    best = float(thresholds[best_idx])
    logger.info("Best threshold=%.4f (F1=%.4f)", best, f1s[best_idx])
    return best


def compute_classification_metrics(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    model_name: str,
    split: str = "test",
    threshold: float = 0.5,
    feature_group: str = "B",
) -> dict:
    """計算分類指標並 append 至 results/metrics.csv。"""
    y_true = np.asarray(y_true)
    y_pred_proba = np.asarray(y_pred_proba)
    y_pred = (y_pred_proba >= threshold).astype(int)

    has_both_classes = len(np.unique(y_true)) > 1
    metrics = {
        "model": model_name,
        "feature_group": feature_group,
        "split": split,
        "timestamp": datetime.utcnow().isoformat(),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_true, y_pred_proba) if has_both_classes else float("nan"),
        "pr_auc": average_precision_score(y_true, y_pred_proba) if has_both_classes else float("nan"),
        "threshold": threshold,
        "n_samples": int(len(y_true)),
        "n_positive": int(y_true.sum()),
    }

    _append_csv(METRICS_CSV, metrics)
    logger.info(
        "[%s/%s] F1=%.4f AUC=%.4f PR-AUC=%.4f",
        model_name, split, metrics["f1"], metrics["auc_roc"], metrics["pr_auc"],
    )
    return metrics


def compute_regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
    split: str = "test",
    feature_group: str = "B",
) -> dict:
    """計算迴歸指標並 append 至 results/regression_metrics.csv。"""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    # RMSLE: 預測值 clip 至 0 以避免 log 負數
    y_pred_clipped = np.clip(y_pred, 0, None)
    rmsle = float(np.sqrt(mean_squared_error(np.log1p(y_true), np.log1p(y_pred_clipped))))
    r2 = r2_score(y_true, y_pred)

    metrics = {
        "model": model_name,
        "feature_group": feature_group,
        "split": split,
        "timestamp": datetime.utcnow().isoformat(),
        "mae": mae,
        "rmse": rmse,
        "rmsle": rmsle,
        "r2": r2,
        "n_samples": int(len(y_true)),
    }

    _append_csv(REGRESSION_METRICS_CSV, metrics)
    logger.info(
        "[%s/%s] MAE=%.4f RMSE=%.4f RMSLE=%.4f R2=%.4f",
        model_name, split, mae, rmse, rmsle, r2,
    )
    return metrics


def _append_csv(path: Path, row: dict) -> None:
    """Append 一列至 CSV，若檔案不存在則先寫 header。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)
