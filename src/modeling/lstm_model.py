"""
2-Layer LSTM + Dropout + Linear Head。

支援兩種任務：
  - task='classification'  → BCEWithLogitsLoss，輸出 logit (scalar)
  - task='regression'      → MSELoss，         輸出 scalar
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor
from torch.nn.utils.rnn import pack_padded_sequence


class LSTMModel(nn.Module):
    """
    Parameters
    ----------
    input_size  : 輸入特徵維度 (預設 3: view, like, comment)
    hidden_size : LSTM 隱藏狀態維度
    num_layers  : LSTM 層數 (設計為 2)
    dropout     : Dropout 比例（作用於 LSTM 層間 + 最後 Linear 前）
    task        : 'classification' 或 'regression'
    """

    def __init__(
        self,
        input_size: int = 3,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
        task: str = "classification",
    ) -> None:
        super().__init__()
        assert task in ("classification", "regression")
        self.task = task
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: Tensor, lengths: Tensor) -> Tensor:
        """
        Parameters
        ----------
        x       : (B, T_max, input_size) — padded sequences
        lengths : (B,) — actual sequence lengths (cpu long tensor)

        Returns
        -------
        out : (B,) — logit (classification) or predicted value (regression)
        """
        # Pack for efficiency with variable-length sequences
        packed = pack_padded_sequence(
            x, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        _, (h_n, _) = self.lstm(packed)
        # h_n: (num_layers, B, hidden_size) — 取最後一層
        last_hidden = h_n[-1]          # (B, hidden_size)
        out = self.dropout(last_hidden)
        out = self.fc(out).squeeze(-1)  # (B,)
        return out
