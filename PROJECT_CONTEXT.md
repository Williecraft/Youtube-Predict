# YouTube 影片流量預測：專案工作清單

這份文件只列專案要做的事情與必要實作細節。

## 0. 固定設定

```text
分類觀測窗：影片發布後 0-3 小時
回歸觀測窗：影片發布後 0-48 小時
主標籤：is_viral_48h
主任務：binary classification，預測 is_viral_48h
副任務：regression，用發布後前 48 小時資料預測接下來 24 小時新增觀看數 log_next_24h_views
切分：依 publish_time 做 train / valid / test，不隨機打散
```

分類 feature 只能使用 0-3 小時內可取得的資料，48h 資料只用來建立分類 label。回歸 feature 只能使用 0-48 小時內可取得的資料，target 是 48-72 小時新增觀看數；48h 當下的累積觀看數可作為回歸 feature，但 48h 之後的資料不能進 feature。

## 1. 建立資料夾與檔案結構

要建立：

```text
data/
├── raw/
│   ├── static/
│   │   ├── videos_static.json
│   │   └── channel_static.json
│   ├── timeseries/by_video/{video_id}.csv
│   └── comments/by_video/{video_id}_t{1,2,3}h.jsonl
├── processed/
│   ├── label_dataset.csv
│   ├── tabular_features.csv
│   ├── regression_dataset.csv
│   ├── regression_features_48h.csv
│   ├── sequences_3h/{video_id}.npy
│   └── sequences_48h/{sample_id}.npy
├── split/
│   ├── train.csv
│   ├── valid.csv
│   └── test.csv
└── state.db                      # SQLite，多主機共用的爬蟲狀態

src/
├── crawler/
├── preprocessing/
├── modeling/
└── utils/

models/
results/
```

設計重點：

- `timeseries` 與 `comments` 一律 per-video 一檔，append-only，多主機輪流跑時用 rsync / git 合併不會打架。
- `state.db` 紀錄影片追蹤狀態（哪些 video 還在追、上次抓到什麼時候、追蹤頻道清單等），跨機器只要把 `state.db` + `data/raw/` 一起搬就完整接手。
- `videos_static.json` 是「id → 靜態欄位」的 dict 結構（單檔即可，靜態資料只寫一次）。`channel_static.json` 同理。

## 2. 爬蟲要做的事

### 2.0 技術選型

全部用 Python `requests`，不靠 YouTube Data API v3、也不靠 yt-dlp。每一種資料都按下面的階梯試，前面失敗才往後退：

1. **InnerTube / 頁面內 JSON**：抓 watch / shorts / search / channel 頁回傳的 `ytInitialData`、`ytInitialPlayerResponse`，或直接 POST `https://www.youtube.com/youtubei/v1/{endpoint}` 取乾淨 JSON。最優先。
2. **HTML scraping**：上面拿不到時改解析 HTML。
3. **Selenium**：以上都失敗才用，會被擋的頁面（例如部分留言載入）才走這條。

通用實作要求：

- 統一 User-Agent、隨機延遲、429 / 5xx 退避（exponential backoff），重試上限 3。
- 失敗的請求寫入 `state.db` 的 `crawl_errors` 表，可重試的之後排程重抓。
- 所有時間欄位寫入時用 UTC ISO 8601 字串。

### 2.1 蒐集影片清單

#### 來源與頻率

| 來源 | 頻率 | 每次目標 | 備註 |
|---|---|---|---|
| `trending` 發燒影片 | 每 15 min | 抓**所有**當前發燒列表上的影片 | 多區合併：先納入 `TW`、`JP`、`US`、`KR`，同 `video_id` 去重；同一 id 再被看到只更新 `last_seen_at`，不重抓 static |
| `search` 搜尋結果 | 每 1 hour | **x = 10** 部新影片/小時 | 從 §2.1.3 關鍵字產生器抽 5–7 個關鍵字，每個搜尋結果頁隨機挑 1–2 部尚未收錄、`age_at_discovery` 越小越優先的影片，湊滿 10 部即停 |
| `channel` 追蹤頻道 | 每 1 hour | **y = 5** 部新影片/小時（上限） | 從 `channel_static.json` 隨機抽追蹤頻道，看 uploads 最近 3 部是否有未收錄的，沒有就抽下一個，直到湊滿 5 部或試完所有頻道；初期頻道少時實際遠少於 5 |

不過濾 `age_at_discovery_minutes`：即使來不及拿到 0–3h 視窗，影片仍可進入回歸（48h 起算的滑動樣本）；只是這支影片不會出現在分類 dataset。

#### 影片清單欄位

每筆 entry 至少包含：

- `video_id`
- `source` ∈ {`trending`, `search`, `channel`}
- `source_detail`（搜尋關鍵字、發燒區域＋排名、來源頻道 id）
- `discovered_at`
- `publish_time`（discovery 當下取得，沒拿到先空著之後補）
- `age_at_discovery_minutes = discovered_at − publish_time`
- `last_seen_at`

存放：寫入 `state.db` 的 `videos` 表，不要為這個再建一個 CSV / JSON。

#### 2.1.3 搜尋關鍵字產生器

兩個來源混用，每次每小時搜尋取 70% 來自 (a)、30% 來自 (b)：

**(a) 種子組合池**：人工準備分類欄位，每次隨機 1–3 個欄位拼接。範例欄位：

```text
{修飾詞} ∈ {最新, 2026, 推薦, 排行, 必看, 開箱, 精選, 爆笑, ...}
{主題}   ∈ {美食, 旅遊, 遊戲, 電影, 動漫, 韓劇, 健身, 投資, AI, 寵物, 育兒, 時事, 科技, 音樂, ...}
{形式}   ∈ {ft, ASMR, vlog, 短片, 教學, 實測, 評測, 反應, 排行榜, ""}
```

組合產生範例：「美食 vlog」、「2026 遊戲推薦」、「韓劇」、「AI 教學」、「開箱 科技」。

**(b) Trending tags 動態抽**：每次跑爬蟲時，從最近 24h 發燒影片的 `tags` 欄位收集高頻 tag，從中隨機抽 1–2 個。

**驗收條件**：實作前先單獨跑 50 次產生器、把生成的關鍵字列出來人工確認沒有亂碼、過於冷門、或語意奇怪的組合，OK 才接到主流程。

### 2.2 爬影片靜態資料

輸出：`data/raw/static/videos_static.json`，結構為 `{video_id: {...static fields...}}` 的單一 JSON dict。

欄位：

| 欄位 | 用途 |
|---|---|
| `video_id` | join key |
| `title` | 算 `title_length` |
| `channel_id` | join 頻道與訂閱數 |
| `publish_time` | 算相對時間窗 |
| `duration_seconds` | 影片基本特徵 |
| `category` | 類別特徵 |
| `tags` | 給 §2.1.3 trending tag 抽樣用，同時算 `tag_count` |
| `tag_count` | metadata / SEO 特徵 |
| `is_shorts` | Shorts / 長影片分流，由 §2.3 結果填入 |
| `static_fetched_at` | 抓取時間 |

每支影片只抓一次靜態資料（除非 `is_shorts == unknown` 才會在判定成功時補回）。

### 2.2.1 追蹤頻道與 channel_static.json

任何被收錄的影片，其 `channel_id` 自動加入追蹤頻道清單。輸出：`data/raw/static/channel_static.json`，結構 `{channel_id: {...}}`。

欄位：

| 欄位 | 用途 |
|---|---|
| `channel_id` | key |
| `channel_title` | 顯示 / debug |
| `subscriber_count` | 訂閱數（最近一次抓到的） |
| `subscriber_count_checked_at` | 訂閱數抓取時間 |
| `country` | 可選 |
| `discovered_at` | 加入追蹤的時間 |
| `discovered_via_video_id` | 因哪部影片被追蹤 |
| `last_checked_at` | 上次掃這個頻道的時間 |
| `last_new_video_at` | 上次在這頻道發現新影片的時間 |

注意 `subscriber_count` 是頻道級別、會持續更新；要算 label 用的 `subscriber_count_at_publish` 必須從**該影片**第一筆 timeseries 紀錄裡取，而不是從 channel_static 取最新值。

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

保存到 `videos_static.json` 的對應 entry：

- `shorts_status_code`
- `shorts_checked_at`
- `is_shorts`

### 2.4 爬時序流量

輸出：`data/raw/timeseries/by_video/{video_id}.csv`，每支影片一個 CSV，append-only。

欄位：

| 欄位 | 用途 |
|---|---|
| `video_id` | join key |
| `crawl_time` | 實際爬取時間（UTC ISO 8601） |
| `time_since_publish_minutes` | 對齊不同影片 |
| `view_count` | label + LSTM |
| `like_count` | LSTM + engagement |
| `comment_count` | LSTM + engagement |
| `subscriber_count` | 頻道規模校正、`subscriber_count_at_publish` 從第一筆取 |
| `video_status` | 過濾不可用影片 |

#### 爬取排程

每支影片從 `discovered_at`（理想情況等於 `publish_time`）開始追蹤到 `publish_time + 168h`（7 天）為止。期間頻率：

| 影片年齡 | 頻率 |
|---|---|
| 0 – 3 h | 每 5–10 min 一筆 |
| 3 – 48 h | 每 1 h 一筆 |
| 48 – 72 h | 每 1 h 一筆，且 48h、72h ±15 min 內必須各有一筆；找不到才於 preprocessing 用線性插補 |
| 72 – 168 h | 每 6 h 一筆即可 |
| > 168 h | 停止追蹤（如機器資源充足可調到 336h，由 `state.db` 的 `track_until` 欄位控制） |

#### 排程實作要求

- `state.db` 的 `videos` 表至少要有 `track_until`、`next_due_at`，scheduler 每次取 `next_due_at <= now AND track_until > now` 的影片來抓，更新成功後重排 `next_due_at`。
- 爬蟲入口純 Python，可被 cron / Windows Task Scheduler / APScheduler 任一啟動，避免綁特定 OS。建議入口：`python -m src.crawler.run_scheduler`。
- 多主機協作靠 `state.db` 的 SQLite WAL + 一個 `lease_until` 欄位（被某主機鎖住的影片在 lease 期限內不會被別台同時抓）。

### 2.5 爬留言

輸出：`data/raw/comments/by_video/{video_id}_t{1,2,3}h.jsonl`，每支影片在 0–3h 內抓 **3 個 snapshot**，分別在 `publish_time + 1h`、`+ 2h`、`+ 3h`（容忍 ±10 min）。

欄位：

- `video_id`
- `comment_id`
- `comment_text`
- `comment_like_count`
- `comment_published_at`（如能拿到）
- `crawl_time`
- `snapshot_label` ∈ {`t1h`, `t2h`, `t3h`}

規則：

- 每個 snapshot 各自抓 top 200 熱門留言（YouTube 預設 "Top comments" 排序）。
- 建分類 feature 時用 `t3h` snapshot 為主，`t1h`、`t2h` 留作早期增長信號（例如 `comment_like_growth_t1h_to_t3h`）。
- 已經錯過某個時間點（例如影片是 `age_at_discovery > 1h` 才被發現）就跳過該 snapshot，不補抓更早的；對應特徵變 NaN，由 preprocessing 處理。

## 3. 前處理要做的事

1. 依 `video_id` 合併 static / timeseries / comments。
2. 把所有時間轉成 UTC 或同一時區。
3. 建立 `time_since_publish_minutes`。
4. 移除 `video_status != public` 的影片。
5. 同影片同時間點重複資料保留最新一筆。
6. 少量缺值線性插補。
7. 缺 0-3h 主要序列的影片排除。
8. 分類資料缺 48h label 的影片排除。
9. 回歸資料缺 48h 輸入端點或 72h target 端點的影片排除。
10. 建立 `log1p` 欄位，例如觀看數、訂閱數。
11. 產出 `label_dataset.csv`、`tabular_features.csv`、`regression_dataset.csv`、`regression_features_48h.csv`、`sequences_3h/{video_id}.npy`、`sequences_48h/{sample_id}.npy`。

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

## 5. 觀看數回歸副主題

副主題：只要某支影片有發布後前 48 小時資訊與 72 小時端點，就建立一筆回歸樣本，用前 48 小時預測接下來 24 小時新增觀看數。

每一筆回歸樣本對應一支影片的一個固定時間窗。

```text
sample_id = {video_id}_first48h
input window = [publish_time, publish_time + 48h]
target window = (publish_time + 48h, publish_time + 72h]
```

不要直接預測 72h 的累積觀看數，因為它會被 48h 累積觀看數強烈支配。改預測 48-72h 的新增觀看數：

```text
views_48h = views at publish_time + 48h
views_72h = views at publish_time + 72h
next_24h_views = max(views_72h - views_48h, 0)

regression_target = log_next_24h_views = log1p(next_24h_views)
predicted_next_24h_views = expm1(predicted_log_next_24h_views)
```

回歸模型輸入：

- 使用 `regression_features_48h.csv`
- LSTM 使用 `sequences_48h/{sample_id}.npy`
- 不可使用 `views_72h` 或 `next_24h_views` 當 feature

`regression_dataset.csv` 至少要有：

- `sample_id`
- `video_id`
- `input_window_start_h`
- `input_window_end_h`
- `target_window_start_h`
- `target_window_end_h`
- `views_48h`
- `views_72h`
- `next_24h_views`
- `log_next_24h_views`

回歸模型要做：

- Linear Regression 或 Ridge Regression baseline
- LightGBM Regressor
- LSTM Regressor

回歸評估指標：

| 指標 | 用途 |
|---|---|
| MAE | 平均差多少觀看數 |
| RMSE | 對大誤差更敏感 |
| RMSLE | 適合長尾觀看數 |
| R2 | 解釋變異比例 |

輸出檔案：

```text
results/regression_metrics.csv
```

`regression_metrics.csv` 至少記錄：

- `target_name`
- `feature_group`
- `model_name`
- `mae`
- `rmse`
- `rmsle`
- `r2`

## 6. 表格特徵要做哪些

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

## 7. Valence-Arousal 要做哪些

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

## 8. LSTM sequence 要做哪些

分類任務輸出：

```text
data/processed/sequences_3h/{video_id}.npy
```

格式：

```text
shape = T x 3
T = 0-3h 內的爬取點，約 18-36 steps
features = [view_count, like_count, comment_count]
```

回歸任務輸出：

```text
data/processed/sequences_48h/{sample_id}.npy
```

格式：

```text
shape = T x 3
T = 0-48h 內的爬取點
features = [view_count, like_count, comment_count]
```

正規化：

- 分類 sequence：每部影片內，各維度除以該維度 0-3h 最大值。
- 回歸 sequence：每個 48h sample 內，各維度除以該維度在該視窗內最大值。
- 最大值為 0 時該維度全設 0。

## 9. 模型要做哪些

### 9.1 Logistic Regression

- 表格 baseline
- 類別欄位 one-hot
- 也作 Stacking meta-learner

### 9.2 LightGBM

- 表格主模型
- 輸出 probability
- 做 SHAP feature importance
- 分類用 LightGBM Classifier
- 回歸用 LightGBM Regressor

### 9.3 LSTM

```text
input = T x 3
model = 2-layer LSTM + Dropout + Linear
loss = BCEWithLogitsLoss
output = probability
```

回歸版本：

```text
input = T x 3
model = 2-layer LSTM + Dropout + Linear
loss = MSELoss on log_next_24h_views
output = predicted_log_next_24h_views
```

### 9.4 Stacking

```text
LightGBM(tabular) -> P1
LSTM(sequence)    -> P2
LogisticRegression(P1, P2) -> final probability
```

Stacking 注意：

- meta-learner 只能用 validation / out-of-fold prediction。
- 不能用 train in-sample prediction 訓練 meta-learner。

## 10. 實驗要跑哪些

資料切分：

```text
train = 最早 70%
valid = 中間 15%
test  = 最晚 15%
```

切分單位是 `video_id`，不是回歸用的 `sample_id`。同一支影片的分類資料與回歸樣本必須留在同一個 split，不能同時出現在 train 和 test。

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
- task type
- feature group
- train / valid / test size
- positive rate
- F1
- AUC-ROC
- Precision
- Recall
- PR-AUC
- MAE
- RMSE
- RMSLE
- R2

## 11. 防資料洩漏規則

- 分類任務：3h 後的資料不能進 feature。
- 分類任務中，`views_48h` 只能做 label。
- 回歸任務：每筆樣本只能使用 0-48h 的資料當 feature。
- `views_72h`、`next_24h_views`、`log_next_24h_views` 只能做 regression target。
- 留言 feature 只能用 0-3h 內留言。
- train / valid / test 依影片發布時間切，且同一 `video_id` 的所有回歸樣本不能跨 split。
- scaler、encoder、threshold 只能 fit train。
- `is_high_growth_48h` 的 median 只能用 train 算。
- Stacking 不能用 base model 的 train in-sample prediction。

## 12. 最後要產出哪些檔案

```text
data/processed/label_dataset.csv
data/processed/tabular_features.csv
data/processed/regression_dataset.csv
data/processed/regression_features_48h.csv
data/processed/sequences_3h/{video_id}.npy
data/processed/sequences_48h/{sample_id}.npy
data/split/train.csv
data/split/valid.csv
data/split/test.csv
results/metrics.csv
results/regression_metrics.csv
results/experiment_summary.csv
results/feature_importance_shap.csv
```

## 13. 實作模組

```text
src/crawler/
  run_scheduler.py            # 主入口：依 state.db 排程觸發各 fetcher
  keyword_generator.py        # §2.1.3 關鍵字產生器，需先單獨驗收
  collect_video_list.py       # 三種來源（trending / search / channel）整合進 state.db
  fetch_trending.py
  fetch_search.py
  fetch_channel_uploads.py
  detect_shorts.py
  fetch_static.py             # 同時更新 channel_static.json
  fetch_timeseries.py
  fetch_comments.py           # 依 snapshot_label 三次

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
  train_regression.py
  train_stacking.py
  evaluate.py
  shap_analysis.py

src/utils/
  io.py
  time.py
  logging.py
  state_db.py                 # SQLite schema、lease 機制、scheduler queue 操作
  http_client.py              # requests session、退避、UA、redirect 控制
```
