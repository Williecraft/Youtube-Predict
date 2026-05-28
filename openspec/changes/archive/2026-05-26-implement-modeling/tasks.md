## 1. 基礎設施與評估工具 (Infrastructure & Evaluation)

- [x] 1.1 建立 `src/modeling/` 目錄與必要的 `__init__.py`。
- [x] 1.2 實作 `evaluate.py`：撰寫分類指標計算函式 (F1, AUC-ROC, Precision, Recall, PR-AUC)，將結果 append 至 `results/metrics.csv`。
- [x] 1.3 實作 `evaluate.py`：撰寫迴歸指標計算函式 (MAE, RMSE, RMSLE, R2)，將結果 append 至 `results/regression_metrics.csv`。
- [x] 1.4 實作資料分割工具函式：基於 `data/processed/label_dataset.csv` 中的 `publish_time`，嚴格依時間序列將資料分割為 Train 70% / Valid 15% / Test 15%。

## 2. 表格特徵基礎模型 (Tabular Models)

- [x] 2.1 實作 `train_logistic.py`：訓練 Logistic Regression baseline 分類器預測 `is_viral_48h`，嚴格過濾確保輸入特徵僅限於 0-3h 範圍。
- [x] 2.2 實作 `train_lightgbm.py` (分類)：訓練 LightGBM 分類模型，處理類別不平衡，並為 Stacking 產生 Out-Of-Fold (OOF) 的預測機率。
- [x] 2.3 實作 `train_regression.py` (LightGBM)：訓練 LightGBM 迴歸模型預測 `log_next_24h_views`，特徵讀取自 `data/processed/regression_features_48h.csv`。
- [x] 2.4 實作 `shap_analysis.py`：載入已訓練的 LightGBM 模型，計算 SHAP values 並匯出至 `results/feature_importance_shap.csv`。

## 3. 深度學習時序模型 (LSTM)

- [x] 3.1 實作 PyTorch LSTM DataLoader：載入 `data/processed/sequences_3h/` (.npy) 檔案進行變長/定長序列的 Dataset 打包處理。
- [x] 3.2 實作 PyTorch LSTM 網路架構：2-Layer LSTM + Dropout + Linear layer (搭配 BCEWithLogitsLoss / MSELoss)。
- [x] 3.3 實作 `train_lstm.py` (分類)：訓練分類模型預測爆紅，保存模型參數，並產生 OOF 預測機率以供 Stacking 使用。
- [x] 3.4 實作 `train_lstm.py` (迴歸)：以相同架構（Head 改為 MSELoss）在 `sequences_48h/` 上訓練迴歸模型預測 `log_next_24h_views`。

## 4. 模型融合 (Stacking Ensemble)

- [x] 4.1 實作 `train_stacking.py`：載入 LightGBM 與 LSTM 階段所產出的 OOF 預測結果。
- [x] 4.2 訓練 Logistic Regression Meta-learner 以結合兩者的預測機率 (P1, P2)，產出融合的最終機率。
- [x] 4.3 進行 Test Set 推論，並將 Stacking 模型的最終指標送入 `evaluate.py` 計算與儲存。
