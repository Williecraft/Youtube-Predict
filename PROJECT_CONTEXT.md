# YouTube 影片流量預測：專案工作清單

這份文件只列專案要做的事情與必要實作細節。

## 0. 固定設定

```text
觀測窗：影片發布後 0-3 小時
主標籤：is_viral_48h
任務：binary classification
切分：依 publish_time 做 train / valid / test，不隨機打散
```

所有 feature 只能使用 0-3 小時內可取得的資料。48h 資料只能用來做 label。

## 1. 建立資料夾與檔案結構

要建立：

```text
data/
├── raw/
│   ├── static/videos_static.json
│   ├── timeseries/video_stats_all.csv
│   └── comments/by_video/{video_id}.jsonl
├── processed/
│   ├── label_dataset.csv
│   ├── tabular_features.csv
│   └── sequences/{video_id}.npy
└── split/
    ├── train.csv
    ├── valid.csv
    └── test.csv

src/
├── crawler/
├── preprocessing/
├── modeling/
└── utils/

models/
results/
```

## 2. 爬蟲要做的事

### 2.1 蒐集影片清單

每筆至少要有：

- `video_id`
- `source`
- `discovered_at`

來源可包含：

- 發燒影片
- 搜尋結果
- 指定頻道近期影片

### 2.2 爬影片靜態資料

輸出：`data/raw/static/videos_static.json`

欄位：

| 欄位 | 用途 |
|---|---|
| `video_id` | join key |
| `title` | 算 `title_length` |
| `channel_id` | join 頻道與訂閱數 |
| `publish_time` | 算相對時間窗 |
| `duration_seconds` | 影片基本特徵 |
| `category` | 類別特徵 |
| `tag_count` | metadata / SEO 特徵 |
| `is_shorts` | Shorts / 長影片分流 |

### 2.3 判定 Shorts

對以下 URL 發 GET，且不要跟隨 redirect：

```text
https://www.youtube.com/shorts/{video_id}
```

判定：

| HTTP status | 結果 |
|---|---|
| `200 OK` | Shorts |
| `303 See Other` | 長影片 |
| 失敗 | `unknown`，之後重試 |

保存：

- `shorts_status_code`
- `shorts_checked_at`

### 2.4 爬時序流量

輸出：`data/raw/timeseries/video_stats_all.csv`

欄位：

| 欄位 | 用途 |
|---|---|
| `video_id` | join key |
| `crawl_time` | 實際爬取時間 |
| `time_since_publish_minutes` | 對齊不同影片 |
| `view_count` | label + LSTM |
| `like_count` | LSTM + engagement |
| `comment_count` | LSTM + engagement |
| `subscriber_count` | 頻道規模校正 |
| `video_status` | 過濾不可用影片 |

爬取頻率：

- 0-3h：每 5-10 分鐘一次
- 48h：至少一筆

### 2.5 爬留言

輸出：`data/raw/comments/by_video/{video_id}.jsonl`

欄位：

- `video_id`
- `comment_id`
- `comment_text`
- `comment_like_count`
- `crawl_time`

規則：

- 每部影片最多保留前 200 則熱門留言。
- 建 feature 時只用 0-3h 內爬到的留言。

## 3. 前處理要做的事

1. 依 `video_id` 合併 static / timeseries / comments。
2. 把所有時間轉成 UTC 或同一時區。
3. 建立 `time_since_publish_minutes`。
4. 移除 `video_status != public` 的影片。
5. 同影片同時間點重複資料保留最新一筆。
6. 少量缺值線性插補。
7. 缺 0-3h 主要序列或缺 48h label 的影片排除。
8. 建立 `log1p` 欄位，例如觀看數、訂閱數。
9. 產出 `label_dataset.csv`、`tabular_features.csv`、`sequences/{video_id}.npy`。

## 4. 爆紅標籤要怎麼做

主定義：**每支影片先算出自己的 48 小時爆紅觀看數門檻，實際 48 小時觀看數達標才算爆紅。**

需要：

- `views_48h`
- `subscriber_count_at_publish`
- `is_shorts`

公式：

```text
effective_subscriber_count = max(subscriber_count_at_publish, 1000)
audience_normalized_views_48h = views_48h / effective_subscriber_count
viral_score_48h = log1p(views_48h) - log1p(effective_subscriber_count)
```

最低觀看門檻：

| 型態 | `min_abs_views_48h` |
|---|---:|
| 長影片 | 2,000 |
| Shorts | 10,000 |

每支影片的正式爆紅觀看數門檻：

```text
viral_view_threshold_48h = max(
    min_abs_views_48h,
    2 * effective_subscriber_count
)
```

主標籤：

```text
is_viral_48h = views_48h >= viral_view_threshold_48h
```

例子：

| 頻道訂閱數 | 型態 | `effective_subscriber_count` | `viral_view_threshold_48h` |
|---:|---|---:|---:|
| 500 | 長影片 | 1,000 | 2,000 |
| 500 | Shorts | 1,000 | 10,000 |
| 10,000 | 長影片 | 10,000 | 20,000 |
| 10,000 | Shorts | 10,000 | 20,000 |
| 100,000 | 長影片 | 100,000 | 200,000 |

爆紅分級：

```text
non_viral   < 1.0x
strong      1.0x - 2.0x
viral       2.0x - 5.0x 且達 48h 最低觀看門檻
super_viral >= 5.0x 且達 48h 最低觀看門檻
```

也要保留 baseline：

```text
growth_rate_48h = views_48h / max(views_3h, 1)
is_high_growth_48h = growth_rate_48h >= median(growth_rate_48h on train)
```

`label_dataset.csv` 至少要有：

- `video_id`
- `is_shorts`
- `publish_time`
- `views_3h`
- `views_48h`
- `subscriber_count_at_publish`
- `effective_subscriber_count`
- `viral_view_threshold_48h`
- `audience_normalized_views_48h`
- `viral_score_48h`
- `is_viral_48h`
- `viral_level_48h`
- `growth_rate_48h`
- `is_high_growth_48h`

## 5. 表格特徵要做哪些

核心特徵：

| 類別 | 特徵 |
|---|---|
| 影片基本 | `duration_seconds`, `category`, `publish_hour`, `is_shorts`, `title_length`, `tag_count` |
| 頻道 | `log_subscriber_count` |
| 早期流量 | `view_growth_rate_1h`, `engagement_rate_early`, `views_per_minute_early` |
| 留言 | `comment_sentiment_score`, `top_comment_like_ratio` |

補充早期流量特徵：

- `views_1h`
- `views_3h`
- `likes_3h`
- `comments_3h`
- `view_delta_0h_1h`
- `view_delta_1h_3h`
- `like_view_ratio_3h`
- `comment_view_ratio_3h`

## 6. Valence-Arousal 要做哪些

每則留言要估：

```text
valence = 情緒正負
arousal = 情緒激動程度
```

彙整成影片特徵：

- `comment_valence_mean`
- `comment_valence_std`
- `comment_arousal_mean`
- `comment_arousal_std`
- `comment_high_arousal_ratio`
- `comment_positive_high_arousal_ratio`
- `comment_negative_high_arousal_ratio`
- `comment_like_weighted_valence`
- `comment_like_weighted_arousal`

初始門檻：

```text
high_valence = valence >= 0.65
low_valence = valence <= 0.35
high_arousal = arousal >= 0.65
```

若沒有直接輸出 Valence-Arousal 的模型：

1. 先用中文情緒模型做多類情緒。
2. 再把情緒類別 mapping 到 valence / arousal。
3. 若做不到，先用 sentiment score 當 valence proxy，用驚嘆號、emoji、強烈語氣詞比例當 arousal proxy。

## 7. LSTM sequence 要做哪些

每部影片輸出：

```text
data/processed/sequences/{video_id}.npy
```

格式：

```text
shape = T x 3
T = 0-3h 內的爬取點，約 18-36 steps
features = [view_count, like_count, comment_count]
```

正規化：

- 每部影片內，各維度除以該維度 0-3h 最大值。
- 最大值為 0 時該維度全設 0。

## 8. 模型要做哪些

### 8.1 Logistic Regression

- 表格 baseline
- 類別欄位 one-hot
- 也作 Stacking meta-learner

### 8.2 LightGBM

- 表格主模型
- 輸出 probability
- 做 SHAP feature importance

### 8.3 LSTM

```text
input = T x 3
model = 2-layer LSTM + Dropout + Linear
loss = BCEWithLogitsLoss
output = probability
```

### 8.4 Stacking

```text
LightGBM(tabular) -> P1
LSTM(sequence)    -> P2
LogisticRegression(P1, P2) -> final probability
```

Stacking 注意：

- meta-learner 只能用 validation / out-of-fold prediction。
- 不能用 train in-sample prediction 訓練 meta-learner。

## 9. 實驗要跑哪些

資料切分：

```text
train = 最早 70%
valid = 中間 15%
test  = 最晚 15%
```

特徵組：

| 組合 | 特徵 |
|---|---|
| A | 影片基本 + 頻道 |
| B | A + 早期流量 |
| C1 | B + binary sentiment |
| C2 | B + Valence-Arousal |
| C3 | B + binary sentiment + Valence-Arousal |

每組要記錄：

- model name
- label name
- feature group
- train / valid / test size
- positive rate
- F1
- AUC-ROC
- Precision
- Recall
- PR-AUC

## 10. 防資料洩漏規則

- 3h 後的資料不能進 feature。
- `views_48h` 只能做 label。
- 留言 feature 只能用 0-3h 內留言。
- train / valid / test 依發布時間切。
- scaler、encoder、threshold 只能 fit train。
- `is_high_growth_48h` 的 median 只能用 train 算。
- Stacking 不能用 base model 的 train in-sample prediction。

## 11. 最後要產出哪些檔案

```text
data/processed/label_dataset.csv
data/processed/tabular_features.csv
data/processed/sequences/{video_id}.npy
data/split/train.csv
data/split/valid.csv
data/split/test.csv
results/metrics.csv
results/experiment_summary.csv
results/feature_importance_shap.csv
```

## 12. 實作模組

```text
src/crawler/
  collect_video_list.py
  detect_shorts.py
  fetch_static.py
  fetch_timeseries.py
  fetch_comments.py

src/preprocessing/
  clean_timeseries.py
  build_labels.py
  build_tabular_features.py
  build_sequences.py
  build_comment_emotion_features.py
  split_dataset.py

src/modeling/
  train_logistic.py
  train_lightgbm.py
  train_lstm.py
  train_stacking.py
  evaluate.py
  shap_analysis.py

src/utils/
  io.py
  time.py
  logging.py
```
