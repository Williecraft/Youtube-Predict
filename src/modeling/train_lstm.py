"""
LSTM 模型訓練腳本（分類 + 迴歸）。

用法：
  python -m src.modeling.train_lstm --task classification
  python -m src.modeling.train_lstm --task regression

分類 (task=classification):
  輸入: sequences_3h/{video_id}.npy + label_dataset.csv (is_viral_48h)
  輸出:
    models/lstm_classifier.pt
    results/lstm_oof_proba.csv   ← OOF 機率（供 Stacking）
    results/lstm_test_proba.csv  ← Test 機率（供 Stacking）
    results/metrics.csv (appended)

迴歸 (task=regression):
  輸入: sequences_48h/{video_id}_first48h.npy + regression_dataset.csv (log_next_24h_views)
  輸出:
    models/lstm_regressor.pt
    results/regression_metrics.csv (appended)
"""

from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import KFold
from torch.utils.data import DataLoader, Subset

from src.modeling.evaluate import (
    compute_classification_metrics,
    find_best_threshold,
    compute_regression_metrics,
)
from src.modeling.lstm_dataset import SequenceDataset, pad_collate_fn
from src.modeling.lstm_model import LSTMModel
from src.modeling.utils import temporal_split
from src.preprocessing.paths import (
    LABEL_DATASET_CSV,
    MODELS_DIR,
    REGRESSION_DATASET_CSV,
    RESULTS_DIR,
    SEQUENCES_3H_DIR,
    SEQUENCES_48H_DIR,
)

logger = logging.getLogger(__name__)

# ── Hyper-parameters ──────────────────────────────────────────────────────────
HIDDEN_SIZE = 64
NUM_LAYERS  = 2
DROPOUT     = 0.3
BATCH_SIZE  = 64
EPOCHS      = 30
LR          = 1e-3
GRAD_CLIP   = 1.0
N_FOLDS     = 5
DEVICE      = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── Data loading ──────────────────────────────────────────────────────────────

def load_classification_data() -> pd.DataFrame:
    df = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id", "is_viral_48h", "publish_time"])
    return df


def load_regression_data() -> pd.DataFrame:
    df = pd.read_csv(
        REGRESSION_DATASET_CSV,
        usecols=["sample_id", "video_id", "log_next_24h_views", "publish_time"],
    )
    return df


# ── Training helpers ──────────────────────────────────────────────────────────

def _train_epoch(
    model: LSTMModel,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
) -> float:
    model.train()
    total_loss = 0.0
    for seqs, lengths, labels in loader:
        seqs    = seqs.to(DEVICE)
        lengths = lengths.to(DEVICE)
        labels  = labels.to(DEVICE)

        optimizer.zero_grad()
        logits = model(seqs, lengths)
        loss   = criterion(logits, labels)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        optimizer.step()
        total_loss += loss.item() * len(labels)
    return total_loss / max(len(loader.dataset), 1)


@torch.no_grad()
def _predict(model: LSTMModel, loader: DataLoader, task: str) -> np.ndarray:
    model.eval()
    preds = []
    for seqs, lengths, _ in loader:
        seqs    = seqs.to(DEVICE)
        lengths = lengths.to(DEVICE)
        logits  = model(seqs, lengths)
        if task == "classification":
            proba = torch.sigmoid(logits).cpu().numpy()
        else:
            proba = logits.cpu().numpy()
        preds.append(proba)
    return np.concatenate(preds) if preds else np.array([])


def _build_model(task: str) -> LSTMModel:
    input_size = 3 if task == "classification" else 4  # 迴歸多一欄 log_max_views
    return LSTMModel(
        input_size=input_size,
        hidden_size=HIDDEN_SIZE,
        num_layers=NUM_LAYERS,
        dropout=DROPOUT,
        task=task,
    ).to(DEVICE)


def _make_loader(dataset: SequenceDataset, shuffle: bool = False) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=shuffle,
        collate_fn=pad_collate_fn,
        num_workers=0,
    )


# ── Classification training ───────────────────────────────────────────────────

def train_classification() -> None:
    df = load_classification_data()
    train_df, valid_df, test_df = temporal_split(df)
    logger.info("CLF Split: train=%d valid=%d test=%d", len(train_df), len(valid_df), len(test_df))

    # ── OOF on train split ────────────────────────────────────────────────
    train_ids    = train_df["video_id"].tolist()
    train_labels = train_df["is_viral_48h"].astype(float).tolist()

    full_train_ds = SequenceDataset(train_ids, train_labels, SEQUENCES_3H_DIR)
    valid_ids     = [v for v in valid_df["video_id"] if (SEQUENCES_3H_DIR / f"{v}.npy").exists()]
    valid_labels  = valid_df.set_index("video_id").loc[valid_ids, "is_viral_48h"].astype(float).tolist()
    test_ids      = [v for v in test_df["video_id"] if (SEQUENCES_3H_DIR / f"{v}.npy").exists()]
    test_labels   = test_df.set_index("video_id").loc[test_ids, "is_viral_48h"].astype(float).tolist()

    valid_ds = SequenceDataset(valid_ids, valid_labels, SEQUENCES_3H_DIR)
    test_ds  = SequenceDataset(test_ids,  test_labels,  SEQUENCES_3H_DIR)

    actual_labels = full_train_ds.get_labels()
    pos_count = float(sum(actual_labels))
    neg_count = float(len(actual_labels) - int(pos_count))
    pw = torch.tensor([neg_count / max(pos_count, 1.0)], dtype=torch.float32).to(DEVICE)
    logger.info("BCEWithLogitsLoss pos_weight=%.2f (pos=%d neg=%d)", pw.item(), int(pos_count), int(neg_count))
    criterion = nn.BCEWithLogitsLoss(pos_weight=pw)

    # KFold OOF
    oof_proba = np.zeros(len(full_train_ds))
    kf = KFold(n_splits=N_FOLDS, shuffle=False)
    indices = list(range(len(full_train_ds)))

    for fold, (tr_idx, val_idx) in enumerate(kf.split(indices)):
        tr_subset  = Subset(full_train_ds, tr_idx)
        val_subset = Subset(full_train_ds, val_idx)
        tr_loader  = DataLoader(tr_subset,  batch_size=BATCH_SIZE, shuffle=True,  collate_fn=pad_collate_fn)
        val_loader = DataLoader(val_subset, batch_size=BATCH_SIZE, shuffle=False, collate_fn=pad_collate_fn)

        model     = _build_model("classification")
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)

        for epoch in range(EPOCHS):
            _train_epoch(model, tr_loader, optimizer, criterion)

        oof_proba[val_idx] = _predict(model, val_loader, "classification")
        logger.info("Fold %d/%d OOF done", fold + 1, N_FOLDS)

    # 儲存 OOF
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    oof_valid_ids    = full_train_ds.get_ids()
    oof_valid_labels = full_train_ds.get_labels()
    oof_df = pd.DataFrame({
        "video_id": oof_valid_ids,
        "lstm_oof_proba": oof_proba,
        "label": oof_valid_labels,
    })
    oof_df.to_csv(RESULTS_DIR / "lstm_oof_proba.csv", index=False)
    logger.info("LSTM OOF 儲存 → results/lstm_oof_proba.csv")

    # ── 最終模型（完整 train，以 valid loss 做早停）───────────────────────
    final_model    = _build_model("classification")
    optimizer      = torch.optim.Adam(final_model.parameters(), lr=LR)
    tr_loader_full = _make_loader(full_train_ds, shuffle=True)
    val_loader     = _make_loader(valid_ds, shuffle=False)

    best_val_loss = float("inf")
    best_state    = None
    patience, wait = 5, 0

    for epoch in range(EPOCHS):
        _train_epoch(final_model, tr_loader_full, optimizer, criterion)
        # validation loss
        final_model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for seqs, lengths, labels in val_loader:
                seqs, lengths, labels = seqs.to(DEVICE), lengths.to(DEVICE), labels.to(DEVICE)
                logits = final_model(seqs, lengths)
                val_loss += criterion(logits, labels).item() * len(labels)
        val_loss /= max(len(valid_ds), 1)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state    = {k: v.clone() for k, v in final_model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                logger.info("Early stopping at epoch %d", epoch + 1)
                break

    if best_state:
        final_model.load_state_dict(best_state)

    # Evaluate
    valid_loader_eval = _make_loader(valid_ds)
    test_loader_eval  = _make_loader(test_ds)

    valid_prob = _predict(final_model, valid_loader_eval, "classification")
    valid_ys   = np.array(valid_labels)[:len(valid_prob)]
    best_thr   = find_best_threshold(valid_ys, valid_prob)
    compute_classification_metrics(valid_ys, valid_prob, model_name="lstm_classifier",
                                   split="valid", threshold=best_thr)
    test_prob = _predict(final_model, test_loader_eval, "classification")
    test_ys   = np.array(test_labels)[:len(test_prob)]
    compute_classification_metrics(test_ys, test_prob, model_name="lstm_classifier",
                                   split="test", threshold=best_thr)

    # Test 機率 for Stacking
    test_proba = _predict(final_model, test_loader_eval, "classification")
    test_proba_df = pd.DataFrame({
        "video_id": test_ds.get_ids(),
        "lstm_test_proba": test_proba,
        "label": test_ds.get_labels(),
    })
    test_proba_df.to_csv(RESULTS_DIR / "lstm_test_proba.csv", index=False)
    logger.info("LSTM Test 機率儲存 → results/lstm_test_proba.csv")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(final_model.state_dict(), MODELS_DIR / "lstm_classifier.pt")
    logger.info("模型儲存 → models/lstm_classifier.pt")


# ── Regression training ───────────────────────────────────────────────────────

def train_regression() -> None:
    df = load_regression_data()
    train_df, valid_df, test_df = temporal_split(df)
    logger.info("REG Split: train=%d valid=%d test=%d", len(train_df), len(valid_df), len(test_df))

    def _filter_existing(rows: pd.DataFrame) -> tuple[list[str], list[float]]:
        ids, labels = [], []
        for _, row in rows.iterrows():
            sid = row["sample_id"]
            if (SEQUENCES_48H_DIR / f"{sid}.npy").exists():
                ids.append(sid)
                labels.append(float(row["log_next_24h_views"]))
        return ids, labels

    tr_ids, tr_labels  = _filter_existing(train_df)
    val_ids, val_labels = _filter_existing(valid_df)
    te_ids,  te_labels  = _filter_existing(test_df)

    train_ds = SequenceDataset(tr_ids,  tr_labels,  SEQUENCES_48H_DIR)
    valid_ds = SequenceDataset(val_ids, val_labels, SEQUENCES_48H_DIR)
    test_ds  = SequenceDataset(te_ids,  te_labels,  SEQUENCES_48H_DIR)

    criterion = nn.MSELoss()
    model     = _build_model("regression")
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    tr_loader  = _make_loader(train_ds, shuffle=True)
    val_loader = _make_loader(valid_ds)
    te_loader  = _make_loader(test_ds)

    best_val_loss = float("inf")
    best_state    = None
    patience, wait = 5, 0

    for epoch in range(EPOCHS):
        _train_epoch(model, tr_loader, optimizer, criterion)
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for seqs, lengths, labels in val_loader:
                seqs, lengths, labels = seqs.to(DEVICE), lengths.to(DEVICE), labels.to(DEVICE)
                preds = model(seqs, lengths)
                val_loss += criterion(preds, labels).item() * len(labels)
        val_loss /= max(len(valid_ds), 1)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state    = {k: v.clone() for k, v in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
            if wait >= patience:
                logger.info("Early stopping at epoch %d", epoch + 1)
                break

    if best_state:
        model.load_state_dict(best_state)

    for split, loader, ys in [
        ("valid", val_loader, np.array(val_labels)),
        ("test",  te_loader,  np.array(te_labels)),
    ]:
        pred = _predict(model, loader, "regression")
        compute_regression_metrics(ys[:len(pred)], pred, model_name="lstm_regressor", split=split)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODELS_DIR / "lstm_regressor.pt")
    logger.info("模型儲存 → models/lstm_regressor.pt")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Train LSTM model")
    parser.add_argument(
        "--task",
        choices=["classification", "regression"],
        default="classification",
        help="分類任務 (sequences_3h) 或 迴歸任務 (sequences_48h)",
    )
    args = parser.parse_args()
    logger.info("Using device: %s", DEVICE)

    if args.task == "classification":
        train_classification()
    else:
        train_regression()


if __name__ == "__main__":
    main()
