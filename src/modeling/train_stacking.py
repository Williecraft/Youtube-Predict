"""
Stacking Ensemble 融合模型。

架構：
  Level-1:  LightGBM 分類機率 (P1) + LSTM 分類機率 (P2)
  Level-2:  Logistic Regression meta-learner (訓練於 OOF 預測)

執行順序：
  1. 先執行 train_lightgbm.py  → results/lgbm_oof_proba.csv, lgbm_test_proba.csv
  2. 先執行 train_lstm.py      → results/lstm_oof_proba.csv,  lstm_test_proba.csv
  3. 再執行本腳本

輸出：
  models/stacking_meta.pkl
  results/metrics.csv (appended, model="stacking_ensemble")
"""

from __future__ import annotations

import logging
import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.modeling.evaluate import compute_classification_metrics, find_best_threshold
from src.preprocessing.paths import MODELS_DIR, RESULTS_DIR

logger = logging.getLogger(__name__)


def load_oof_predictions() -> tuple[np.ndarray, np.ndarray]:
    """
    載入 LightGBM 與 LSTM 的 OOF 機率，透過 video_id 對齊後合併。

    Returns
    -------
    X_oof   : (N, 2) — [lgbm_oof_proba, lstm_oof_proba]
    y_oof   : (N,)   — 標籤（取 LightGBM OOF 的 label）
    """
    lgbm_oof_path = RESULTS_DIR / "lgbm_oof_proba.csv"
    lstm_oof_path = RESULTS_DIR / "lstm_oof_proba.csv"

    if not lgbm_oof_path.exists():
        raise FileNotFoundError(f"找不到 {lgbm_oof_path}，請先執行 train_lightgbm.py")
    if not lstm_oof_path.exists():
        raise FileNotFoundError(f"找不到 {lstm_oof_path}，請先執行 train_lstm.py --task classification")

    lgbm_oof = pd.read_csv(lgbm_oof_path)  # video_id, lgbm_oof_proba, label
    lstm_oof  = pd.read_csv(lstm_oof_path)  # video_id, lstm_oof_proba, label

    merged = lgbm_oof.merge(lstm_oof[["video_id", "lstm_oof_proba"]], on="video_id", how="inner")
    logger.info("OOF 合併後樣本數: %d (lgbm=%d, lstm=%d)", len(merged), len(lgbm_oof), len(lstm_oof))

    X_oof = merged[["lgbm_oof_proba", "lstm_oof_proba"]].values
    y_oof = merged["label"].values
    return X_oof, y_oof


def load_test_predictions() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """
    載入 Test set 的 LightGBM 與 LSTM 機率，透過 video_id 對齊。

    Returns
    -------
    X_test      : (N, 2) — [lgbm_test_proba, lstm_test_proba]
    y_test      : (N,)   — 標籤
    video_ids   : list[str]
    """
    lgbm_test_path = RESULTS_DIR / "lgbm_test_proba.csv"
    lstm_test_path = RESULTS_DIR / "lstm_test_proba.csv"

    if not lgbm_test_path.exists():
        raise FileNotFoundError(f"找不到 {lgbm_test_path}，請先執行 train_lightgbm.py")
    if not lstm_test_path.exists():
        raise FileNotFoundError(f"找不到 {lstm_test_path}，請先執行 train_lstm.py --task classification")

    lgbm_test = pd.read_csv(lgbm_test_path)  # video_id, lgbm_test_proba, label
    lstm_test  = pd.read_csv(lstm_test_path)  # video_id, lstm_test_proba, label

    merged = lgbm_test.merge(lstm_test[["video_id", "lstm_test_proba"]], on="video_id", how="inner")
    logger.info("Test 合併後樣本數: %d", len(merged))

    X_test    = merged[["lgbm_test_proba", "lstm_test_proba"]].values
    y_test    = merged["label"].values
    video_ids = merged["video_id"].tolist()
    return X_test, y_test, video_ids


def train() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # ── 4.1 載入 OOF ─────────────────────────────────────────────────────
    X_oof, y_oof = load_oof_predictions()

    # ── 4.2 訓練 meta-learner ─────────────────────────────────────────────
    meta = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42)
    meta.fit(X_oof, y_oof)
    logger.info("Meta-learner 訓練完成 (OOF size=%d, pos_rate=%.2f%%)",
                len(y_oof), 100 * y_oof.mean())

    oof_proba = meta.predict_proba(X_oof)[:, 1]
    best_thr = find_best_threshold(y_oof, oof_proba)
    compute_classification_metrics(
        y_oof, oof_proba, model_name="stacking_ensemble", split="oof_train", threshold=best_thr
    )

    # ── 4.3 Test Set 推論 ─────────────────────────────────────────────────
    X_test, y_test, video_ids = load_test_predictions()
    test_proba = meta.predict_proba(X_test)[:, 1]
    compute_classification_metrics(
        y_test, test_proba, model_name="stacking_ensemble", split="test", threshold=best_thr
    )

    # 儲存 test 融合結果
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_df = pd.DataFrame({
        "video_id": video_ids,
        "stacking_proba": test_proba,
        "label": y_test,
    })
    result_df.to_csv(RESULTS_DIR / "stacking_test_proba.csv", index=False)
    logger.info("Stacking test 結果儲存 → results/stacking_test_proba.csv")

    # 儲存 meta-learner
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "stacking_meta.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"meta": meta}, f)
    logger.info("Meta-learner 儲存 → %s", model_path)


if __name__ == "__main__":
    train()
