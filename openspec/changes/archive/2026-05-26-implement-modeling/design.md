## Context
YouTube 影片爆紅預測專案目前已完成資料爬蟲 (Crawler) 與前處理 (Preprocessing) 的開發。前處理會輸出供後端模型使用的特徵與標籤檔案：
- `label_dataset.csv`
- `tabular_features.csv`
- `regression_dataset.csv`
- `regression_features_48h.csv`
- `sequences_3h/*.npy` 和 `sequences_48h/*.npy`

目前尚未實作任何模型訓練與評估 (Modeling & Evaluation) 程式碼。我們需要在 `src/modeling/` 目錄中搭建四種機器學習模型（Logistic Regression, LightGBM, LSTM, Stacking Ensemble），並確保模型能正確進行分類任務（預測 48h 爆紅標籤 `is_viral_48h`）與迴歸任務（預測 48h-72h 觀看成長數 `log_next_24h_views`），同時包含評估驗證與 SHAP 解釋分析機制。

## Goals / Non-Goals

**Goals:**
- 建立分類模型腳本 (`train_logistic.py`, `train_lightgbm.py`, `train_lstm.py`)。
- 建立迴歸模型腳本 (`train_regression.py`)。
- 建立融合表格與時序特徵預測的腳本 (`train_stacking.py`)。
- 提供模型評估腳本 (`evaluate.py`) 計算分類 (F1, AUC, PR-AUC 等) 與迴歸 (MAE, RMSE 等) 指標。
- 提供 SHAP 分析腳本 (`shap_analysis.py`) 解釋表格特徵。
- 嚴格遵守 Data Leakage 防護規則（如：以 publish_time 進行 Temporal Split、特徵依時間窗嚴格隔離）。

**Non-Goals:**
- 本變更不包含自然語言的情緒抽取模型（如 Valence-Arousal）開發，該部分將於日後加入，本設計僅需預留特徵組 Ablation (A, B, C1, C2, C3) 的組合架構。
- 本變更不涉及建立即時推論 (Real-time Inference) 的 API，僅處理離線實驗訓練。

## Decisions

1. **資料分割策略 (Temporal Split)**
   - 依據 `publish_time` 進行排序分割：Train 70% (最早), Valid 15% (中間), Test 15% (最晚)。同一 `video_id` 禁止跨 Split。
   - **Rationale**: 符合「以歷史預測未來」的真實業務邏輯，避免隨機打散造成的資料外洩 (Temporal Data Leakage)。

2. **Stacking Ensemble 架構**
   - 將 LightGBM 產出的機率值 (P1) 與 LSTM 產出的機率值 (P2) 作為 Logistic Regression (Meta-learner) 的輸入。Meta-learner 必須基於 OOF (Out-Of-Fold) 預測進行訓練。
   - **Rationale**: 直接使用 Training set 的 in-sample 預測會產生嚴重過擬合；必須透過 OOF 來擬合 meta-learner 的權重。

3. **深度學習框架選型 (LSTM)**
   - 採用 PyTorch 實作 2-Layer LSTM + Dropout + Linear 網路架構。
   - **Rationale**: PyTorch 對於自定義 Loss (例如 BCEWithLogitsLoss / MSELoss) 以及變長時序資料的處理具有高度彈性。

4. **實驗結果輸出與追蹤**
   - 所有的實驗評估指標會一律以 append 形式寫入 `results/metrics.csv`（分類）與 `results/regression_metrics.csv`（迴歸）。
   - **Rationale**: 有利於後續跨實驗、跨特徵組合（Ablation）對比，無需依賴繁重的第三方追蹤工具。

## Risks / Trade-offs

- [Risk] 時序特徵中存在極端值 (Outliers)，可能影響 LSTM 收斂 → [Mitigation] 前處理已有各維度局部最大值正規化 (Normalization)，LSTM 訓練時會加上 Gradient Clipping 避免梯度爆炸。
- [Risk] 資料不平衡問題 (爆紅影片占比極低) → [Mitigation] 分類模型採用 `scale_pos_weight` (LightGBM/LogReg) 處理類別不平衡，並以 PR-AUC 作為首要的評估指標。
