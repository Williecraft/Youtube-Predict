# YouTube 影片早期成長與爆紅預測

> 資料探勘導論期末專題報告底稿
> 爬蟲停止日期：2026-06-10
> 模型流程執行日期：2026-06-10
> 本文件可直接作為報告基底，再依課程格式補上組員、課程資訊與分工。

---

## 摘要

本專題建立一套 YouTube 影片資料蒐集與爆紅預測系統，核心問題有二：（1）能否使用發布後前 3 小時的資料預測影片 48 小時內是否爆紅（分類）；（2）能否使用前 48 小時資料預測接下來 24 小時的新增觀看數（迴歸）。

資料蒐集於 2026-06-10 停止，固定快照包含 **1,916 筆**分類樣本（病毒率 **12.6%**）與 **2,394 筆**迴歸樣本，Shorts 與長影片比例約 34%：66%。為避免 Shorts 集中於測試集造成評估偏差，採用**分組時序切分**（Shorts 與長影片各自按發布時間 70/15/15 分割再合併），每個切分的 Shorts 比例均維持 34%。

分類任務在五個特徵群組（A–C3）和四種模型架構上進行 Ablation Study。測試集最佳單模為 **LightGBM Group C2**（F1=**0.763**、AUC=0.934）；以 AUC 為首要指標則 **LightGBM C1** 最佳（AUC=**0.943**、F1=0.752）；Stacking 整合模型 AUC=0.919。迴歸任務中，LightGBM Group C1 測試集 **R²=0.853**、MAE=0.835（`log1p` 尺度）。SHAP 分析顯示頻道訂閱數（`log_subscriber_count`，SHAP=2.109）是最關鍵特徵，其次為發布後 3 小時觀看數（`views_3h`=0.770）與 1–3h 增量（`view_delta_1h_3h`=0.683）。

---

## 1. 研究背景與動機

### 1.1 問題描述

YouTube 影片的觀看成長具有高度不均衡性：多數影片觀看量有限，少數在發布後數小時內快速擴散。這種「爆紅」現象對創作者策略、廣告投放與平台推薦演算法均有重要意涵。若能在發布初期預測後續表現，可協助各方提早辨識潛力影片。

本專題聚焦兩個可操作的預測問題：

1. **分類任務**：使用影片發布後前 **3 小時**的資料，預測影片在 **48 小時**內是否達到「爆紅」門檻（`is_viral_48h`）。
2. **迴歸任務**：使用影片發布後前 **48 小時**的資料，預測接下來 **24 小時**的新增觀看數（`log_next_24h_views`）。

此外，本專題額外探討：（1）留言情緒特徵是否能提升預測效果；（2）Shorts 與長影片的分布偏斜如何影響模型評估的公平性。

### 1.2 相關研究方向

- **社群媒體病毒傳播預測**：早期工作（如 Szabo & Huberman, 2010）發現 YouTube 影片的早期觀看數與長期成長呈 log-scale 線性關係，奠定早期流量作為預測特徵的理論基礎。
- **YouTube 爆紅預測**：多項研究（如 Jain et al., 2014；Zhao et al., 2015）指出，發布後 1–6 小時的觀看速度是最具預測力的早期信號，頻道訂閱數則是最強的靜態特徵。
- **序列模型 vs 表格模型**：在有限訓練樣本下，Gradient Boosting 等表格模型通常優於 LSTM，因序列模型對資料量更敏感（Grinsztajn et al., 2022）。
- **留言情緒分析**：近期研究顯示，發布初期留言的情緒極性與觀看成長存在正相關，但在低覆蓋率條件下效果受限（Chen et al., 2023）。

---

## 2. 系統架構

```
Shorts 頁面 / fresh_search 發現
        │
        ▼
  影片 ID 蒐集 (crawler/run_scheduler.py)
        │
        ├─── 靜態資訊抓取 → data/raw/static/videos_static.json
        │
        ├─── 時序排程（0h/1h/3h/48h/72h）→ data/raw/timeseries/by_video/*.csv
        │
        └─── 留言快照（t1h/t2h/t3h）→ data/raw/comments/by_video/*.jsonl
                │
                ▼
  src/preprocessing/run_all.py:
    clean_timeseries → build_labels → split_dataset
        │
        ├─── build_tabular_features → data/processed/tabular_features.csv
        │
        ├─── build_sequences → data/processed/sequences_3h/*.npy
        │                                      sequences_48h/*.npy
        ├─── build_regression_dataset → data/processed/regression_dataset.csv
        │
        └─── build_comment_emotion_features → data/processed/comment_features.csv
                │
                ▼
  src/modeling/:
    train_logistic / train_lightgbm / train_lstm → results/metrics.csv
    train_stacking                               → results/stacking_test_proba.csv
    train_regression / train_lstm (reg)          → results/regression_metrics.csv
    shap_analysis                                → results/feature_importance_shap.csv
                │
                ▼
  src/visualization/generate_figures.py → results/figures/fig01–fig17
```

---

## 3. 資料蒐集

### 3.1 蒐集內容

| 資料類型 | 主要欄位 |
|---|---|
| 影片靜態資訊 | `video_id`、標題、發布時間、影片長度、分類（category）、標籤數、是否 Shorts、頻道 ID |
| 時間序列 | 抓取時間、發布後分鐘數（`time_since_publish_minutes`）、觀看數、按讚數、留言數、頻道訂閱數、影片狀態 |
| 留言快照 | 影片 ID、快照時點（t1h/t2h/t3h）、留言文字、留言按讚數 |

**Shorts 偵測**：對 `/shorts/{video_id}` URL 發送 HTTP 請求，返回 200 → Shorts；303 重導向 → 長影片。

### 3.2 蒐集規模

| 項目 | 數量 |
|---|---:|
| 分類可用樣本 | 1,916 |
| 迴歸可用樣本 | 2,394 |
| Tabular feature rows（across all videos）| 33,895 |
| 有 t3h 留言快照、可建情緒特徵的影片 | 642 |

爬蟲後期切換為 **Shorts-only 發現模式**（`DISCOVERY_DISABLED = True`），目的是補足 Shorts 比例。兩類影片均是分析對象，`is_shorts` 本身也是 Group A 以上的模型特徵。

### 3.3 資料集描述統計

**影片類型分布：**

| 類型 | 樣本數 | Viral 數 | Viral 率 |
|---|---:|---:|---:|
| Shorts | 644 | 89 | **13.8%** |
| 長影片 | 1,272 | 152 | **11.9%** |
| 合計 | 1,916 | 241 | **12.6%** |

**觀看數分位（views_48h）：**

| 分位 | views_48h |
|---|---:|
| 中位數（50th） | 1,119 |
| 75th | 7,509 |
| 90th | 42,610 |
| 95th | 109,486 |
| 99th | 481,699 |
| 最大值 | 4,942,905 |

分布高度右偏（長尾），92% 的影片 views_48h ≤ 50,000，但少數影片可達數百萬次。

**訂閱數分位（subscriber_count_at_publish）：**

| 分位 | 訂閱數 |
|---|---:|
| 中位數 | 22,350 |
| 75th | 286,750 |
| 90th | 2,110,000 |

**Viral vs Non-viral 早期訊號對比：**

| 分組 | views_3h 中位數 | views_3h 平均 |
|---|---:|---:|
| Viral | 1,312 | 48,055 |
| Non-viral | 184 | 3,974 |

3 小時觀看數的中位數差距超過 7 倍，確認早期流量是爆紅的強力預測信號。

![病毒率分布](results/figures/fig03_viral_rate_by_type.png)
![觀看 CDF](results/figures/fig02_view_cdf_by_type.png)
![影片類別分布](results/figures/fig04_category_distribution.png)

---

## 4. 資料前處理

### 4.1 時間序列清理

1. 抓取時間統一轉為 UTC datetime。
2. 依靜態資料中的發布時間重新計算 `time_since_publish_minutes`。
3. 移除 `UNPLAYABLE`、`LOGIN_REQUIRED` 等非正常狀態的 snapshot。
4. 對同一影片、同一分鐘的重複 snapshot 去重（保留觀看數較高者）。
5. 對 Shorts 影片的時序，在插值前以**前後最大值約束**，防止補值超過已知最大觀看數造成資料洩漏。

### 4.2 Checkpoint 對齊規則

模型所需的 0h/1h/3h/48h/72h 快照，從清理後的時序內尋找最近的觀測值，容許誤差如下：

| Checkpoint | 容許誤差 |
|---|---:|
| 0h | ±15 分鐘 |
| 1h | ±15 分鐘 |
| 3h | ±20 分鐘 |
| 48h | ±90 分鐘 |
| 72h | ±120 分鐘 |

### 4.3 爆紅標籤定義

設計原則：**同時考量絕對觀看量與頻道受眾規模**，對小頻道保留較低門檻，對 Shorts 設較高絕對門檻（反映短影音平台的較高傳播速度）。

```
effective_subscriber_count  = max(subscriber_count_at_publish, 1000)
min_abs_views_48h           = 10,000  (Shorts)
                            = 2,000   (長影片)
viral_view_threshold_48h    = max(min_abs_views_48h, 2 × effective_subscriber_count)
is_viral_48h                = 1  if  views_48h ≥ viral_view_threshold_48h  else  0
```

**門檻範例：**

| 頻道訂閱數 | 影片類型 | 計算過程 | 門檻 |
|---:|---|---|---:|
| 500 | Shorts | max(10,000, 1,000×2) | 10,000 |
| 500 | 長影片 | max(2,000, 1,000×2) | 2,000 |
| 8,000 | Shorts | max(10,000, 8,000×2) | 16,000 |
| 8,000 | 長影片 | max(2,000, 8,000×2) | 16,000 |
| 100,000 | 任意 | max(10,000, 100,000×2) | 200,000 |

### 4.4 迴歸目標

迴歸預測 48h 後的 24h 新增觀看數，取 `log1p` 轉換以處理長尾分布：

```
next_24h_views      = max(views_72h − views_48h, 0)
log_next_24h_views  = log1p(next_24h_views)
```

### 4.5 分組時序切分（解決 Shorts 偏斜問題）

**問題**：直接對全部影片做時序切分，會因 Shorts 集中在後期爬蟲才大量加入，導致測試集幾乎全為 Shorts，訓練集則幾乎全為長影片，形成評估偏差。

**解法：分組時序切分**：Shorts 與長影片各自按發布時間排序，各自做 70/15/15 切割，最後合併。

| Split | 樣本數 | Shorts 比例 |
|---|---:|---:|
| Train | 1,133 | ~34% |
| Valid | 380 | ~34% |
| Test | 403 | ~34% |

各切分 Shorts 比例均維持約 34%，確保模型訓練與評估的影片類型分布一致。

![資料切分平衡](results/figures/fig01_data_split_balance.png)

---

## 5. 特徵工程

### 5.1 特徵群組（Ablation Study 設計）

| 群組 | 特徵內容 | 特徵數 |
|---|---|---:|
| **A** | 靜態特徵：`duration_seconds`、`publish_hour`、`is_shorts`、`title_length`、`tag_count`、`log_subscriber_count` | 6 |
| **B** | A + 早期流量：`views_1h/3h`、`likes_3h`、`comments_3h`、`view_delta_0h_1h/1h_3h`、`view_growth_rate_1h`、`views_per_minute_early`、`like_view_ratio_3h`、`comment_view_ratio_3h`、`engagement_rate_early`、`log_views_3h/likes_3h/comments_3h` | 20 |
| **C1** | B + 留言二元情緒：`comment_sentiment_score`、`top_comment_like_ratio`、`comment_count_3h` | 23 |
| **C2** | B + Valence-Arousal proxy：`comment_valence_mean/std`、`comment_arousal_mean/std`、`comment_high_arousal_ratio` | 25 |
| **C3** | B + C1 + C2（全部留言特徵）| 28 |

### 5.2 留言情緒特徵建立方法（Group C1/C2）

**Group C1 — Binary Sentiment**：
- 模型：`uer/roberta-base-finetuned-jd-binary-chinese`（HuggingFace，中文影評二分類）
- 每則 t3h snapshot 留言推論 positive 機率分數
- 影片層級彙整：`comment_sentiment_score`（均值）、`top_comment_like_ratio`（按讚前 5 則的正向比例）、`comment_count_3h`（留言數）

**Group C2 — Valence-Arousal proxy**：
- Valence：直接使用 sentiment score 作為效價 proxy
- Arousal（喚醒度）proxy：以正規表達式計算驚嘆號密度 + emoji 密度 + 強烈詞彙（哇/好棒/OMG/震驚⋯）出現率，不需額外模型
- 影片層級彙整：均值、標準差、高喚醒比例（≥ 0.65）

**覆蓋率**：642 部影片有 t3h 留言快照，約佔分類樣本的 **34%**，其餘以 0 填補。

### 5.3 LSTM Sequence 格式

- **分類**：`T × 3` 陣列 `[view_count, like_count, comment_count]`，覆蓋 0–3h，T ≈ 18–36 點（5–10 分鐘間隔）。每個欄位以該影片時間窗內最大值正規化（防止跨影片規模差異）。
- **迴歸**：`T × 4` 陣列（額外加入 `log1p(max_views_in_window)`），覆蓋 0–48h。

### 5.4 SHAP 特徵重要性（LightGBM Group B，test set，n=288）

| 排名 | 特徵 | Mean Absolute SHAP | 說明 |
|---:|---|---:|---|
| 1 | `log_subscriber_count` | **2.109** | 頻道既有受眾規模 |
| 2 | `views_3h` | 0.770 | 發布後 3h 累計觀看數 |
| 3 | `view_delta_1h_3h` | 0.683 | 1–3h 觀看增量（成長動能）|
| 4 | `likes_3h` | 0.411 | 3h 按讚數 |
| 5 | `title_length` | 0.327 | 標題字元數 |
| 6 | `publish_hour` | 0.272 | 發布時段（UTC）|
| 7 | `duration_seconds` | 0.231 | 影片長度 |
| 8 | `engagement_rate_early` | 0.178 | 早期互動率（按讚+留言/觀看）|
| 9 | `views_per_minute_early` | 0.109 | 每分鐘觀看速度 |
| 10 | `tag_count` | 0.097 | 標籤數量 |

`log_subscriber_count`（SHAP=2.109）重要性遠高於其他特徵，顯示**頻道既有受眾規模是爆紅的基礎條件**。`views_3h` 與 `view_delta_1h_3h` 的 SHAP 值約為第二層級（0.68–0.77），反映**早期成長動能是最重要的即時信號**。

![SHAP 特徵重要性](results/figures/fig06_shap_importance.png)
![早期觀看數 vs 是否爆紅](results/figures/fig07_views3h_vs_viral.png)
![觀看增量分布](results/figures/fig08_growth_rate_dist.png)
![留言 Valence-Arousal 散布圖](results/figures/fig17_comment_valence_arousal.png)
![成長曲線範例](results/figures/fig05_growth_curve_examples.png)

---

## 6. 實驗設計

### 6.1 模型組合

| 任務 | 模型 | 特徵群組 | 說明 |
|---|---|---|---|
| 分類 | Logistic Regression | A, B, C1 | StandardScaler + `class_weight='balanced'` |
| 分類 | LightGBM | A, B, C1, C2, C3 | 5-Fold OOF，scale_pos_weight 自動計算 |
| 分類 | LSTM | B | `T×3` 序列，BCEWithLogitsLoss + pos_weight |
| 分類 | Stacking | B | LightGBM B OOF + LSTM OOF → Logistic Regression meta |
| 迴歸 | LightGBM | B, C1 | Early stopping on RMSE |
| 迴歸 | LSTM | B | `T×4` 序列，MSELoss |

### 6.2 Stacking 架構

```
LightGBM(tabular)  ──(5-Fold OOF)──▶  P₁ [n_train × 1]
LSTM(sequence)     ──(5-Fold OOF)──▶  P₂ [n_train × 1]
                                        │
                          [P₁, P₂]  →  LogisticRegression  →  final P
```

Meta-learner 在 train split 的 OOF 預測上訓練（非 in-sample），符合防洩漏要求。評估時兩個 base model 以完整 train split 重新訓練，再對 test set 各自生成機率後輸入 meta-learner。

### 6.3 超參數設定

**LightGBM 分類器：**

| 參數 | 值 |
|---|---|
| objective | binary |
| metric | average_precision |
| num_leaves | 63 |
| learning_rate | 0.05 |
| feature_fraction (colsample) | 0.8 |
| bagging_fraction (subsample) | 0.8 |
| bagging_freq | 5 |
| num_boost_round（上限）| 500 |
| early_stopping | patience=50 round |
| scale_pos_weight | neg/pos（train set 計算）≈ 7.6 |
| OOF Folds | 5-Fold，非隨機（按時序）|
| random_state | 42 |

**LightGBM 迴歸器：**

| 參數 | 值 |
|---|---|
| objective | regression |
| metric | rmse |
| num_leaves | 63 |
| learning_rate | 0.05 |
| feature_fraction | 0.8 |
| bagging_fraction | 0.8 |
| num_boost_round（上限）| 500 |
| early_stopping | patience=50 round |

**LSTM（分類 & 迴歸）：**

| 參數 | 值 |
|---|---|
| hidden_size | 64 |
| num_layers | 2 |
| dropout | 0.3 |
| batch_size | 64 |
| optimizer | Adam，lr=1e-3 |
| gradient_clip | 1.0 |
| max_epochs | 30 |
| early_stopping | patience=5（valid loss）|
| input_size | 3（分類）/ 4（迴歸）|

**Logistic Regression（分類）：**

| 參數 | 值 |
|---|---|
| solver | lbfgs |
| max_iter | 1,000 |
| class_weight | balanced |
| preprocessing | StandardScaler（fit on train only）|

### 6.4 評估指標定義

**分類指標**（all computed on test set，使用 valid set 選定最佳 threshold）：

| 指標 | 公式 / 說明 |
|---|---|
| **F1** | 2 × Precision × Recall / (Precision + Recall)；F1 同時考量精確率與召回率 |
| **Precision** | TP / (TP + FP)；預測為 viral 中實際為 viral 的比例 |
| **Recall** | TP / (TP + FN)；所有實際 viral 影片被正確預測到的比例 |
| **AUC-ROC** | ROC 曲線下面積；0.5=隨機，1.0=完美；對門檻選擇不敏感 |
| **PR-AUC** | Precision-Recall 曲線下面積；在類別不平衡時比 AUC-ROC 更具分辨力 |

門檻選擇：以 valid set 上最大化 F1 的 threshold 為準，再應用到 test set。

**迴歸指標**（all on `log_next_24h_views` 尺度）：

| 指標 | 公式 | 說明 |
|---|---|---|
| **MAE** | mean(|y − ŷ|) | 平均絕對誤差，單位與目標相同（log scale） |
| **RMSE** | √mean((y − ŷ)²) | 均方根誤差，對大誤差更敏感 |
| **RMSLE** | √mean((log(1+y) − log(1+ŷ))²) | 注意：目標已取 log1p，此為二次 log 轉換後的誤差，數值較小 |
| **R²** | 1 − SS_res/SS_tot | 決定係數，越接近 1 越好；報告主要指標 |

### 6.5 防洩漏規範

1. **分類特徵**：只使用 0–3h checkpoint 資料（不包含 48h 觀看數）
2. **迴歸特徵**：只使用 0–48h checkpoint 資料（不包含 72h 觀看數）
3. **留言**：只使用 t3h snapshot 內的留言（t3h ≈ 3 小時）
4. **Scaler/Encoder**：僅在 train split fit，transform 應用到 valid/test
5. **Meta-learner**：只在 OOF 預測（不含 in-sample）上訓練，test set 完全未見
6. **Split 映射**：所有模型讀取同一份 `split_map.csv`，確保相同 video_id 不跨 split

---

## 7. 實驗結果

### 7.1 分類測試集完整結果（n=403，n_positive=52）

| 模型 | 群組 | F1 | Precision | Recall | AUC-ROC | PR-AUC |
|---|---|---:|---:|---:|---:|---:|
| Logistic | A | 0.283 | 0.171 | 0.808 | 0.643 | 0.209 |
| Logistic | B | 0.520 | 0.368 | 0.885 | 0.905 | 0.649 |
| Logistic | C1 | 0.528 | 0.373 | **0.904** | 0.907 | 0.650 |
| LightGBM | A | 0.327 | 0.310 | 0.346 | 0.733 | 0.280 |
| LightGBM | B | 0.731 | 0.731 | 0.731 | 0.937 | 0.800 |
| LightGBM | C1 | 0.752 | 0.776 | 0.731 | **0.943** | 0.818 |
| **LightGBM** | **C2** | **0.763** | **0.822** | 0.712 | 0.934 | 0.809 |
| LightGBM | C3 | 0.740 | 0.771 | 0.712 | 0.939 | **0.832** |
| LSTM | B | 0.257 | 0.157 | 0.705 | 0.590 | 0.146 |
| Stacking | B | 0.674 | 0.611 | 0.750 | 0.919 | 0.783 |

**關鍵觀察：**
- Group A → B 是最大跳躍：LightGBM F1 0.327 → 0.731（+0.404），AUC 0.733 → 0.937（+0.204）
- 加入留言情緒（B → C1/C2/C3）帶來小幅但一致改善：F1 +0.01 至 +0.03
- C2（Valence-Arousal）在 F1 和 Precision 上優於 C1（Binary Sentiment）
- C3（全部留言特徵）PR-AUC 最高（0.832），但 F1 略低於 C2（0.740 vs 0.763）
- Logistic B 的 Recall 最高（0.885），適合需要盡量不遺漏爆紅影片的場景

![ROC 曲線](results/figures/fig09_roc_curves.png)
![PR 曲線](results/figures/fig10_pr_curves.png)
![混淆矩陣（LightGBM B）](results/figures/fig11_confusion_matrix_lgbm.png)
![閾值敏感度（LightGBM B）](results/figures/fig12_threshold_sensitivity.png)

### 7.2 Ablation Study（分類）

![Ablation 分類比較](results/figures/fig13_ablation_classification.png)

LightGBM 的 Ablation 結果清楚顯示：
1. **A → B 是關鍵躍升**：加入早期流量特徵後 F1 從 0.327 提升至 0.731（+122%）
2. **B → C 有正向邊際效益**：即使僅 34% 覆蓋率，情緒特徵仍有貢獻
3. **C2 在 F1/Precision 上最佳**：Valence-Arousal 代理特徵有效補充二元情緒的資訊

### 7.3 迴歸測試集完整結果（n=211）

| 模型 | 群組 | MAE | RMSE | RMSLE | R² |
|---|---|---:|---:|---:|---:|
| LightGBM | B | 0.841 | 1.172 | 0.343 | 0.851 |
| **LightGBM** | **C1** | **0.835** | **1.162** | **0.332** | **0.853** |
| LSTM | B | 1.137 | 1.610 | 0.445 | 0.705 |

（指標皆在 `log_next_24h_views` 尺度，log scale 下 MAE=0.835 對應實際觀看數約 ×e^0.835 ≈ 2.3 倍誤差）

LightGBM C1 以微幅優勢（R² 0.853 vs 0.851）為最佳。LSTM R²=0.705 顯著低於 LightGBM，因為序列模型缺乏靜態特徵的支撐。

![預測 vs 實際（LightGBM C1）](results/figures/fig14_reg_pred_vs_actual.png)
![殘差分布](results/figures/fig15_reg_residuals.png)

### 7.4 Ablation Study（迴歸）

![Ablation 迴歸比較](results/figures/fig16_ablation_regression.png)

---

## 8. 結果討論

### 8.1 為何 LightGBM 遠優於 LSTM

| 面向 | LightGBM | LSTM |
|---|---|---|
| 最關鍵特徵 | 可直接使用 `log_subscriber_count`（SHAP=2.109）| 序列只有觀看/按讚/留言，無訂閱數 |
| 資料量需求 | 1,133 train 樣本已足夠 | 正類只有 136 個，序列模型學習困難 |
| 類別不平衡 | `scale_pos_weight` 直接設定 | `pos_weight≈6.6` 使模型趨向全預測正類 |
| 訓練穩定性 | Boosting 架構本身穩定 | 早停在 epoch 9，泛化不足 |

### 8.2 留言情緒特徵的效益分析

在 34% 覆蓋率的限制下，C 系列相對 B 的具體改善：

| 比較 | F1 變化 | AUC 變化 | PR-AUC 變化 |
|---|---:|---:|---:|
| B → C1 | +0.021 | +0.006 | +0.018 |
| B → C2 | +0.032 | −0.003 | +0.009 |
| B → C3 | +0.009 | +0.002 | +0.032 |

**C2（Valence-Arousal）在 F1 和 Precision 改善最大**，顯示喚醒度（arousal）proxy 提供了超出純情緒極性的額外資訊（高喚醒留言 → 觀眾更興奮 → 更高病毒性）。若覆蓋率提升至 70% 以上，改善幅度預期更明顯。

### 8.3 Stacking 效果分析

Stacking 測試集 F1=0.674（低於 LightGBM B 的 0.731），但 AUC=0.919（僅略低於 LightGBM C1 的 0.943）。LSTM 的機率品質較差（AUC=0.590），在融合時拉低了整體 F1。若 LSTM 能改善至 AUC>0.8，Stacking 的 F1 預期可超越單一 LightGBM。

### 8.4 分組時序切分的重要性

舊切分（直接時序排序）→ test 幾乎全 Shorts、train 幾乎全長影片，評估結果基本無效。新分組切分確保各 split 均有約 34% Shorts，模型能從均衡分布中學習，評估也更具代表性。

---

## 9. 限制

1. **留言情緒覆蓋率偏低（34%）**：C 系列特徵雖有正向效果，但仍有 66% 樣本以 0 填補；若能提升覆蓋率，效益預期更顯著。
2. **LSTM 缺乏靜態特徵**：目前序列模型不含訂閱數等強特徵，是分類 F1 只有 0.257 的主因。若在序列模型中加入靜態特徵輸入分支，表現應大幅提升。
3. **資料已固定**：爬蟲於 2026-06-10 停止，結果基於此 fixed snapshot，未涵蓋之後的影片成長變化。
4. **長尾分布**：迴歸 RMSE 受少數極熱門影片影響偏高，MAE 更具一般性參考價值。
5. **單一隨機種子**：LightGBM 的 random_state=42、LSTM 未固定種子，未做多次實驗的穩定性評估。
6. **無超參數搜尋**：模型超參數均為人工設定，未做 Grid/Random Search，存在進一步優化空間。

---

## 10. 結論

本專題完成一套端到端的 YouTube 影片爆紅預測系統，從資料蒐集、前處理、特徵工程，到多模型 Ablation Study 與 SHAP 可解釋性分析。主要發現如下：

1. **發布後 3 小時的資料已足以有效預測 48 小時爆紅**。LightGBM Group B 測試集 F1=0.731、AUC=0.937；加入留言情緒後最佳可達 F1=0.763（C2）、AUC=0.943（C1）。
2. **頻道訂閱數是最關鍵的單一特徵**（SHAP=2.109），早期觀看速度（`views_3h`=0.770、`view_delta_1h_3h`=0.683）是第二層級的即時信號，兩者合力解釋了模型的主要預測能力。
3. **留言情緒在低覆蓋率下仍有效益**。C1/C2/C3 在 34% 覆蓋率下相對 B 各有 F1 +0.009 至 +0.032 的改善，顯示留言情緒是值得持續追蹤的補充特徵。
4. **分組時序切分是保證評估公平性的必要設計**。若不做分組切分，Shorts 集中於 test set 的偏差會使評估結果失去意義。
5. **LightGBM 迴歸 R²=0.853**（Group C1），在 log1p 尺度下 MAE=0.835，可為創作者提供合理的 24h 新增觀看數預測。

---

## 11. 後續工作

1. **提升留言覆蓋率**（目前 34%）：以更完整的情緒資料評估 C 系列特徵的潛力。
2. **LSTM 多模態輸入**：在序列輸入旁加入靜態特徵分支（訂閱數、影片長度等），解決序列模型缺乏強靜態特徵的問題。
3. **分類型模型（Shorts vs Long 分開建模）**：兩類影片的成長模式不同，可比較是否需要獨立的特徵集與門檻。
4. **超參數搜尋**：對 LightGBM 做 Optuna/RandomSearch，對 LSTM 調整 hidden_size、num_layers、learning_rate。
5. **多種子穩定性評估**：重複 3–5 次實驗，報告均值與標準差，增加結果可信度。
6. **Attention / Transformer 序列模型**：若資料量能增加至 5,000+ 樣本，可嘗試 Transformer encoder 取代 LSTM。
