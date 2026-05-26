## Why

目前專案的爬蟲機制已經開發完成並穩定收集了大量影片的靜態資訊、時序流量資料以及留言。與此同時，前處理（Preprocessing）模組的程式碼也已就緒。為了加速專案進度，我們不需等待資料庫累積完所有生命週期的資料，即可基於已收集到的資料先一步實作後端的資料建模與評估流程 (Modeling & Evaluation)。這個變更旨在搭建機器學習模型的訓練 Pipeline，驗證演算法在早期特徵（0–3h 與 0–48h）上的預測成效，從而達成預測 YouTube 影片是否爆紅（Classification）與新增觀看數（Regression）的核心研究目標。

## What Changes

- 建立 `src/modeling/` 目錄與訓練/評估腳本。
- 實作基於表格特徵的 Logistic Regression Baseline 模型 (`train_logistic.py`)。
- 實作基於表格特徵的 LightGBM 模型 (`train_lightgbm.py`)。
- 實作基於時序特徵 (T×3 序列) 的 LSTM 深度學習模型 (`train_lstm.py`)。
- 實作觀看數迴歸預測模型 (`train_regression.py`)。
- 實作整合 LightGBM 與 LSTM 機率輸出的 Stacking Ensemble 融合模型 (`train_stacking.py`)。
- 實作分類任務與迴歸任務的模型評估機制 (`evaluate.py`)。
- 實作基於 LightGBM 的 SHAP 特徵重要性分析模組 (`shap_analysis.py`)。
- 落實時間序列分割機制 (Train 70% / Valid 15% / Test 15%)，並確保嚴格防範 Data Leakage（嚴格遵守 Classification 僅使用 0–3h、Regression 僅使用 0–48h 資料的限制）。

## Capabilities

### New Capabilities
- `classification-models`: 分類任務模型（Logistic Regression, LightGBM, LSTM），預測 `is_viral_48h`，特徵範圍限於發布後 0–3h。
- `regression-models`: 迴歸任務模型，使用發布後 0–48h 的資料預測接下來的 `log_next_24h_views`。
- `stacking-ensemble`: Stacking 架構實作，以 Out-Of-Fold (OOF) 預測訓練 meta-learner。
- `model-evaluation`: 分類指標 (F1, AUC-ROC, PR-AUC 等)、迴歸指標 (MAE, RMSE, R² 等) 的計算與 SHAP 解釋性分析。

### Modified Capabilities


## Impact

- 新增 `src/modeling/` 模組，不影響現有 `crawler` 與 `preprocessing` 的運作。
- 模型訓練依賴於 `data/processed/` 目錄下產生的 `label_dataset.csv`, `tabular_features.csv` 與 `.npy` 序列檔。
- 將會產出實驗指標至 `results/metrics.csv`, `results/regression_metrics.csv`, `results/experiment_summary.csv` 等檔案。
