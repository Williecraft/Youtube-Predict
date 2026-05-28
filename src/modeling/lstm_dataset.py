"""
PyTorch Dataset / DataLoader for LSTM sequence models.

序列格式（由 build_sequences.py 產出）：
  sequences_3h/{video_id}.npy            → shape (T, 3), T ≈ 18–36
  sequences_48h/{video_id}_first48h.npy  → shape (T, 3)
  features = [view_count, like_count, comment_count]，已正規化至 [0, 1]

SequenceDataset 支援可變長度序列：
  - 將同一 batch 內的序列 padding 至最長長度
  - 提供 pad_collate_fn 供 DataLoader 使用
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import Tensor
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data import Dataset


class SequenceDataset(Dataset):
    """
    載入 .npy 序列檔 + 標籤，供 LSTM 訓練使用。

    Parameters
    ----------
    ids : list[str]
        video_id（分類）或 sample_id（迴歸，格式 {video_id}_first48h）。
    labels : list[float]
        對應的目標值（分類: 0/1；迴歸: log_next_24h_views）。
    seq_dir : Path
        存放 .npy 檔的目錄。
    """

    def __init__(self, ids: list[str], labels: list[float], seq_dir: Path) -> None:
        self.ids = ids
        self.labels = labels
        self.seq_dir = seq_dir
        self._valid: list[int] = []

        # 預先檢查哪些 npy 存在
        for i, sid in enumerate(ids):
            if (seq_dir / f"{sid}.npy").exists():
                self._valid.append(i)

    def __len__(self) -> int:
        return len(self._valid)

    def __getitem__(self, idx: int) -> tuple[Tensor, Tensor]:
        i = self._valid[idx]
        arr = np.load(self.seq_dir / f"{self.ids[i]}.npy")   # (T, 3)
        arr = arr.astype(np.float32)
        seq = torch.from_numpy(arr)                            # (T, 3)
        label = torch.tensor(self.labels[i], dtype=torch.float32)
        return seq, label

    def get_ids(self) -> list[str]:
        """回傳實際載入的 id 列表（僅含 npy 存在的）。"""
        return [self.ids[i] for i in self._valid]

    def get_labels(self) -> list[float]:
        return [self.labels[i] for i in self._valid]


def pad_collate_fn(
    batch: list[tuple[Tensor, Tensor]],
) -> tuple[Tensor, Tensor, Tensor]:
    """
    將可變長度序列 batch padding 成 (B, T_max, 3)。

    Returns
    -------
    padded_seqs : Tensor  shape (B, T_max, 3)
    lengths      : Tensor  shape (B,)  — 各序列實際長度
    labels       : Tensor  shape (B,)
    """
    seqs, labels = zip(*batch)
    lengths = torch.tensor([s.shape[0] for s in seqs], dtype=torch.long)
    padded = pad_sequence(seqs, batch_first=True, padding_value=0.0)  # (B, T_max, 3)
    labels_t = torch.stack(labels)
    return padded, lengths, labels_t
