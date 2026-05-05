# YouTube 影片流量預測與留言互動特徵分析：Project Context

本文件是此專案的主要說明書與後續實作依據。它整合了 `Proposal/YouTube_Prediction_Final.pptx.pdf`、`Proposal/Proposal.md` 與期中提案後老師的口頭回饋，目標是讓任何接手此專案的人都能清楚知道：這個題目要解決什麼問題、資料怎麼來、特徵怎麼定義、模型怎麼做、如何評估，以及「爆紅」標籤應該如何穩定且明確地標註。

## 0. 來源優先順序與閱讀原則

### 0.1 來源文件

- 最終簡報 PDF：`Proposal/YouTube_Prediction_Final.pptx.pdf`
- 文字提案：`Proposal/Proposal.md`
- 簡報規劃與逐頁腳本：`Proposal/Presentation_slides.csv`
- 提案要求：`Proposal/Proposal_requirements.txt`
- 簡報技巧整理：`Proposal/Presentation_techniques.md`

### 0.2 衝突處理規則

若 `Proposal.md` 與 `YouTube_Prediction_Final.pptx.pdf` 內容衝突，以 `YouTube_Prediction_Final.pptx.pdf` 為準。

`Proposal.md` 的價值是補足最終簡報沒有展開的細節，例如資料清理規則、儲存架構、模型訓練細節、留言情緒模型選型與實驗邏輯。最終簡報則是老師與同學實際聽到的版本，因此在專案定位、頁面重點、模型名單、feature 清單與預期成果上優先採用 PDF。

老師期中提案回饋中的兩點是新增需求，應納入後續實作規格：

1. `Valence-Arousal` 可以作為更完整的情緒 feature。
2. 必須定義一個穩定、好用、明確的「爆紅」標準，否則無法正確標註影片到底是不是爆紅。

這兩點不視為和提案衝突，而是對原提案的補強。

## 1. 專案基本資訊

### 1.1 題目

YouTube 影片流量預測與留言互動特徵分析

### 1.2 課程與報告性質

- 課程：資料探勘導論
- 報告：期末專題提案
- 提案形式：15 分鐘口頭報告 + 5 分鐘 Q&A

### 1.3 最終簡報封面資訊

最終 PDF 封面列出的組員：

- 張哲維
- 張子善
- 林鈺紳
- 蔡秉融

### 1.4 專案一句話摘要

本專題想用 YouTube 影片公開資料、影片發布早期的流量時間序列、留言互動與情緒特徵，預測影片後續是否會出現高成長或爆紅表現，並比較傳統表格式機器學習、時間序列深度學習與 stacking ensemble 的效果。

## 2. 研究動機

### 2.1 為什麼做這個題目

YouTube 是最大的創作者舞台之一，創作者與觀眾在影音平台上的互動高度密集。對創作者來說，一支影片發布後最焦慮、也最有價值的資訊通常不是最終觀看數，而是發布後前幾小時的觀看數曲線：它有沒有被推起來、互動是不是夠強、留言是否熱烈、平台是否開始推薦。

最終簡報用「觀看數成長示意：發布後 48 小時」呈現兩種典型走勢：

- 爆紅影片：早期成長速度快，後續曲線持續上升。
- 平淡影片：早期成長慢，後續逐漸趨緩。

提案的核心直覺是：如果早期流量曲線、互動數據與留言反應真的反映推薦系統與觀眾興趣，那麼我們應該可以用這些訊號預測影片後續的觀看數成長表現。

### 2.2 現有問題

目前一般創作者或資料分析初學者缺乏簡單且可重複的開放工具來分析 YouTube 影片成長行為。YouTube 後台資料不是公開資料，YouTube API 也有配額與欄位限制，因此本專題希望盡量使用公開頁面可取得的資訊，建立一個可重複執行的資料探勘流程。

### 2.3 研究價值

本專案的價值不只是訓練一個分類器，而是建立一套完整流程：

- 如何蒐集影片資料。
- 如何把原始流量紀錄整理成時序與表格特徵。
- 如何定義可訓練的二元標籤。
- 如何比較不同模型的歸納假設。
- 如何用對照實驗回答「哪些特徵真的有幫助」。
- 如何用 SHAP 或其他解釋方法理解影響影片成長的關鍵因素。

## 3. 核心研究問題與目標

### 3.1 核心問題

最終簡報中的核心問題：

> 能否透過影片公開資料、早期流量與留言互動特徵，預測 YouTube 影片的觀看數成長表現？

實作時應把此問題轉成一個明確的 supervised learning 任務：

- 輸入：影片發布後早期可取得的資料。
- 輸出：影片在指定未來時間窗是否達到「爆紅」或高成長標準。
- 任務型態：二元分類。

### 3.2 四個研究目標

最終簡報列出四個目標：

1. 建立 YouTube 爬蟲流程：蒐集靜態資訊、時序流量與留言資料。
2. 設計具分析意義的特徵：每個特徵都應該有清楚的理論假設。
3. 比較傳統機器學習與深度學習：以 LightGBM 與 LSTM 為主要代表。
4. 找出哪類特徵最有貢獻：透過分階段對照實驗量化。

## 4. 資料來源與資料型態

### 4.1 資料來源

資料由自行撰寫的 Python 爬蟲取得，來源是 YouTube 公開頁面可見資訊。最終簡報強調：

- 自行爬蟲。
- 不依賴 YouTube API key 作為主要流程。
- 不建資料庫，優先使用文字檔保存。
- 資料格式包含 JSON、CSV、JSONL，方便用 Pandas 與一般 Python 工具處理。

### 4.2 三大資料類別

最終簡報將資料分成三大類。

#### 4.2.1 靜態資訊 `STATIC`

- 儲存格式：JSON
- 代表內容：影片不會變動，或變動對此專案不重要的資料。
- 範例：影片標題、影片長度、是否為 Shorts。

欄位：

| 欄位 | 說明 | 後續用途 |
|---|---|---|
| `video_id` | 影片唯一識別碼 | 所有資料表 join key |
| `title` | 影片標題 | 計算 `title_length`，也可延伸做文字特徵 |
| `channel_id` | 頻道識別碼 | 連結頻道資料與訂閱數 |
| `publish_time` | 發布時間 | 建立時間切分、發布時段特徵 |
| `duration_seconds` | 影片長度秒數 | 影片基本特徵 |
| `category` | 影片分類 | 類別特徵與分層比較 |
| `tag_count` | 標籤數量 | 反映 SEO 或 metadata 完整度 |
| `is_shorts` | 是否為 Shorts | 分開建模與分層評估的核心欄位 |

注意：`Proposal.md` 中部分段落使用 `publish_hour` 作為表格特徵；最終 PDF 第 12 頁列的是 `publish_time`。實作時以 `publish_time` 作為原始欄位，並可從中衍生 `publish_hour`、`publish_weekday`、`publish_hour_bucket` 等模型用特徵。文件與資料表命名應清楚區分原始欄位與衍生欄位。

#### 4.2.2 時序流量 `TIME`

- 儲存格式：CSV
- 代表內容：影片每個時間點的公開狀態。
- 更新頻率：每 5-10 分鐘更新一次。

欄位：

| 欄位 | 說明 | 後續用途 |
|---|---|---|
| `video_id` | 影片唯一識別碼 | join key |
| `crawl_time` | 爬取時間 | 建立時間序列 |
| `time_since_publish` | 距離發布經過時間 | 對齊不同影片的相對時間 |
| `view_count` | 觀看數 | 主要目標與 LSTM 輸入 |
| `like_count` | 按讚數 | 互動強度與 LSTM 輸入 |
| `comment_count` | 留言數 | 互動強度與 LSTM 輸入 |
| `subscriber_count` | 頻道訂閱數 | 頻道規模控制變項 |
| `video_status` | 影片狀態 | 過濾刪除、私人或不可用影片 |

#### 4.2.3 留言資料 `COMMENT`

- 儲存格式：JSONL
- 代表內容：影片下方公開留言。
- 爬取頻率：每 2 小時爬一次。
- 每部影片保留：前 200 則留言，優先使用熱門留言。

欄位：

| 欄位 | 說明 | 後續用途 |
|---|---|---|
| `video_id` | 影片唯一識別碼 | join key |
| `comment_id` | 留言唯一識別碼 | 去重 |
| `comment_text` | 留言文字 | 情緒分析、Valence-Arousal 特徵 |
| `comment_like_count` | 留言按讚數 | 熱門留言權重與 `top_comment_like_ratio` |
| `crawl_time` | 爬取時間 | 避免特徵洩漏，切出觀測窗內留言 |

## 5. 建議資料儲存架構

`Proposal.md` 建議的資料夾架構如下，後續實作應盡量沿用：

```text
youtube_traffic_project/
├── data/
│   ├── raw/
│   │   ├── static/videos_static.json
│   │   ├── timeseries/video_stats_all.csv
│   │   └── comments/by_video/{video_id}.jsonl
│   ├── processed/
│   │   ├── tabular_features.csv
│   │   ├── sequences/
│   │   └── label_dataset.csv
│   └── split/
│       ├── train.csv
│       ├── valid.csv
│       └── test.csv
├── src/
│   ├── crawler/
│   ├── preprocessing/
│   ├── modeling/
│   └── utils/
├── models/
└── results/
```

設計理由：

- 靜態資料用 JSON：`video_id` 作為 key，自然適合查詢與合併。
- 時序資料用 CSV 長表：方便 Pandas groupby、resample、interpolation。
- 留言資料用 JSONL：逐行讀取可避免記憶體壓力，也方便單支影片增量寫入。
- processed 與 raw 分開：避免模型訓練直接依賴爬蟲原始格式。
- split 單獨保存：確保所有模型與對照實驗使用同一組 train/valid/test。

## 6. Shorts 與長影片自動判定

### 6.1 為什麼要判定 Shorts

Shorts 與長影片在觀看情境、推薦邏輯、使用者停留行為、互動比例與生命週期上差異很大。若混在同一個資料集訓練，模型可能學到格式差異，而不是影片本身是否有爆紅潛力。

因此最終簡報明確要求：

- 判定 `is_shorts`。
- Shorts 與長影片分開建模。
- 或至少在切分、評估與標籤標準中分層處理。

### 6.2 判定方法

對下列 URL 發送 HTTP GET，且不跟隨 redirect：

```text
https://www.youtube.com/shorts/{video_id}
```

依 HTTP 狀態碼判定：

| HTTP 狀態碼 | 判定 |
|---|---|
| `303 See Other` | 長影片 |
| `200 OK` | Shorts |

### 6.3 方法優點

- 不需要 YouTube API key。
- 可在建立影片清單時即時標記。
- 可自動化整合至爬蟲流程。
- 可降低 Shorts 與長片混用造成的演算法雜訊。

### 6.4 實作注意事項

- HTTP client 必須設定不要自動跟隨 redirect，否則會看不到原始 303。
- YouTube 前端行為可能改版，若狀態碼規則失效，需要建立 fallback 檢查。
- 建議保存 `shorts_check_url`、`shorts_status_code`、`shorts_checked_at`，方便除錯。
- 若請求失敗，不要直接當作長影片；應標記 `is_shorts = null` 或 `unknown`，待重試。

## 7. 分析流程總覽

最終簡報第 11 頁將 pipeline 分成五個階段：

1. 資料蒐集：爬蟲 + Shorts 自動判定。
2. 資料清理：去重、插補、`log1p` 轉換。
3. 特徵工程：12 個表格特徵 + LSTM 時序序列。
4. 模型訓練：LR / LGB / LSTM / Stack。
5. 模型解釋：SHAP + 對照實驗。

每個階段都應該有明確輸入與輸出，確保流程完整、可重複執行。

## 8. 資料清理規格

### 8.1 時序資料去重

同一支影片若同一個相對時間點或同一個爬取時間附近有多筆資料，保留最新一筆或品質最高的一筆。去重後應確保 `(video_id, crawl_time)` 不重複。

### 8.2 時間對齊

不同影片發布時間不同，因此模型不應直接使用絕對 `crawl_time` 排序，而應轉成：

```text
time_since_publish = crawl_time - publish_time
```

後續 LSTM 序列、早期流量特徵與 label 都應使用相對時間窗。

### 8.3 缺失值處理

- 時序中間少數缺失：可使用線性插補。
- 整段缺失或缺少關鍵時間窗：排除該影片。
- 訂閱數缺失：可使用該頻道附近時間點的最近值；若完全缺失，另設 missing flag。
- 留言缺失：不要自動當作負面情緒，應區分「沒有留言」與「留言未爬到」。

### 8.4 不可用影片

若影片被刪除、轉私人、年齡限制導致無法穩定取得資料，應從訓練資料排除，或至少以 `video_status` 標記並在實驗中說明。

### 8.5 長尾分布處理

觀看數與訂閱數通常高度長尾，應使用：

```text
log1p(x) = log(1 + x)
```

常見欄位：

- `log_view_count`
- `log_subscriber_count`
- `log_comment_count`
- `log_like_count`

注意：LSTM 輸入與 LightGBM 表格特徵不一定要使用同一種尺度，但轉換方式必須在 preprocessing 中固定，避免不同實驗不可比。

## 9. 特徵設計

最終簡報的表格特徵共 12 個，分成四類：影片基本、頻道、早期流量、留言情緒。

### 9.1 影片基本特徵

| 特徵 | 來源 | 假設 |
|---|---|---|
| `duration_seconds` | 靜態資訊 | 影片長度會影響觀看完成率、推薦與使用情境 |
| `category` | 靜態資訊 | 不同分類的流量分布與觀眾行為不同 |
| `publish_time` | 靜態資訊 | 發布時間影響初期曝光；可衍生發布小時與星期 |
| `is_shorts` | Shorts 判定 | Shorts 與長片演算法行為差異極大 |
| `title_length` | `title` 衍生 | 標題長度反映資訊量、吸引力或 SEO 策略 |
| `tag_count` | 靜態資訊 | 標籤數量反映 metadata 完整度或 SEO 積極程度 |

### 9.2 頻道特徵

| 特徵 | 來源 | 假設 |
|---|---|---|
| `log_subscriber_count` | 時序流量或頻道頁面 | 訂閱數是初始曝光的重要控制變項，取 log 降低長尾偏斜 |

### 9.3 早期流量特徵

觀測窗建議使用發布後前 3 小時，與最終簡報的 LSTM 輸入一致。

| 特徵 | 定義 | 假設 |
|---|---|---|
| `view_growth_rate_1h` | 前 1 小時觀看數成長率 | 首小時成長率是後續擴散最直接的訊號 |
| `engagement_rate_early` | `(likes + comments) / max(views, 1)` | 反映觀眾互動強度 |
| `views_per_minute_early` | 觀測窗內每分鐘觀看數 | 衡量初期速度，並可搭配訂閱數解釋 |

建議補充衍生欄位：

- `views_1h`
- `views_3h`
- `likes_3h`
- `comments_3h`
- `view_delta_0h_1h`
- `view_delta_1h_3h`
- `like_view_ratio_3h`
- `comment_view_ratio_3h`

這些衍生欄位不一定全部進入最終模型，但有助於 EDA 與除錯。

### 9.4 留言情緒特徵

最終簡報第 14 頁使用：

```text
uer/roberta-base-finetuned-jd-binary-chinese
```

流程：

1. 每部影片取前 200 則留言。
2. 對留言批次推論。
3. 取得正向機率或情緒分數。
4. 彙整為 `comment_sentiment_score`，範圍 0-1。

原提案還有：

| 特徵 | 定義 | 假設 |
|---|---|---|
| `comment_sentiment_score` | 留言平均正向情緒分數 | 留言整體情緒傾向可能影響或反映擴散 |
| `top_comment_like_ratio` | 最熱門留言按讚數 / 觀看數 | 反映是否有高共鳴留言帶動互動 |

## 10. 老師回饋：Valence-Arousal 情緒特徵

### 10.1 為什麼需要 Valence-Arousal

原提案使用 binary sentiment，主要捕捉「正向 vs 負向」。但 YouTube 留言的傳播價值不一定只由正負情緒決定。例如：

- 很正向但低 arousal：溫和稱讚，可能不會帶動大量互動。
- 很負向但高 arousal：爭議、憤怒、吵架，可能提高留言數與擴散。
- 中性但高 arousal：驚訝、震撼、困惑，也可能代表討論度高。
- 正向且高 arousal：興奮、爆笑、感動，可能對爆紅有正向影響。

因此老師提到的 `Valence-Arousal` 可以把留言情緒從單一分數升級成二維情緒空間。

### 10.2 定義

| 維度 | 中文解釋 | 低分代表 | 高分代表 |
|---|---|---|---|
| `Valence` | 情緒效價、愉悅度 | 負面、不愉快、批評、厭惡 | 正面、愉快、喜歡、稱讚 |
| `Arousal` | 情緒喚起度、激動程度 | 平靜、冷淡、低刺激 | 激動、興奮、憤怒、驚訝、高刺激 |

### 10.3 對本專案的意義

`Valence` 接近原本的 `comment_sentiment_score`，但 `Arousal` 是新增資訊。Arousal 可以捕捉「留言是否有能量」，對 YouTube 擴散可能很重要，因為高 arousal 內容更容易促成留言、轉傳、爭論或二創。

### 10.4 建議新增特徵

以影片為單位彙整留言的 Valence-Arousal：

| 特徵 | 定義 | 用途 |
|---|---|---|
| `comment_valence_mean` | 留言 valence 平均 | 整體正負傾向 |
| `comment_valence_std` | 留言 valence 標準差 | 留言意見是否分歧 |
| `comment_arousal_mean` | 留言 arousal 平均 | 留言整體激動程度 |
| `comment_arousal_std` | 留言 arousal 標準差 | 情緒強度是否分歧 |
| `comment_high_arousal_ratio` | arousal 高於門檻的留言比例 | 討論是否高能量 |
| `comment_positive_high_arousal_ratio` | valence 高且 arousal 高的留言比例 | 興奮、喜歡、爆笑、感動 |
| `comment_negative_high_arousal_ratio` | valence 低且 arousal 高的留言比例 | 爭議、憤怒、吵架 |
| `comment_like_weighted_valence` | 以留言按讚數加權的 valence | 熱門留言的主流情緒 |
| `comment_like_weighted_arousal` | 以留言按讚數加權的 arousal | 熱門留言的情緒強度 |

### 10.5 門檻建議

若模型輸出 valence 與 arousal 都正規化到 0-1，可先使用：

```text
high_valence = valence >= 0.65
low_valence = valence <= 0.35
high_arousal = arousal >= 0.65
```

實際門檻應在訓練集上根據分布檢查，避免所有留言都落在同一側。若分布偏移很大，可改用訓練集分位數，例如 arousal top 30% 作為 high arousal。

### 10.6 避免資料洩漏

如果模型的觀測窗是發布後前 3 小時，留言情緒與 Valence-Arousal 也只能使用 `crawl_time <= publish_time + 3h` 的留言。24 小時後才出現的留言不能用於預測 24 小時標籤，否則會資料洩漏。

### 10.7 實作選項

優先順序建議：

1. 若找到可離線執行、支援中文的 Valence-Arousal 或 emotion regression 模型，直接輸出二維分數。
2. 若只有中文情緒分類模型，先輸出多類情緒，再用固定 mapping 轉成 Valence-Arousal。例如喜悅為高 valence 高 arousal，憤怒為低 valence 高 arousal，悲傷為低 valence 中低 arousal。
3. 若時間不足，保留原 `comment_sentiment_score` 作為 valence proxy，另用情緒強度或標點符號、驚嘆號、emoji、強烈語氣詞比例近似 arousal。

最低可交付版本：

- `comment_valence_mean`
- `comment_arousal_mean`
- `comment_high_arousal_ratio`

完整版本再加入加權與分歧特徵。

## 11. LSTM 時序輸入設計

最終簡報第 13 頁定義：

```text
input shape = T x 3
```

每個時間步包含：

```text
view_count
like_count
comment_count
```

T 的定義：

- 使用影片發布後前 3 小時的爬取點。
- 每 5-10 分鐘爬取一次。
- 約 18-36 個時間步。

正規化：

- 每個維度以自身最大值歸一化。
- 目的：消除 views、likes、comments 的量綱差異。

LSTM 的角色：

- 學習成長加速度。
- 學習爆發點。
- 學習平台期。
- 捕捉表格特徵難以手工表達的動態模式。

與 LightGBM 的互補：

- LightGBM 擅長靜態欄位與人工摘要特徵。
- LSTM 擅長原始序列與時間動態。

## 12. 「爆紅」標籤定義

### 12.1 為什麼必須重新定義

老師指出需要定義一個穩定、好用、明確的「爆紅」，這是整個 supervised learning 任務的核心。若標籤不清楚，模型就算分數高，也可能只是在學習一個模糊或不合理的目標。

原 `Proposal.md` 提到以「發布後 24 小時觀看數成長率」並用樣本中位數切成高成長與低成長。這可以作為 baseline，但它比較像「高於樣本中位數的成長影片」，不一定等於一般語意上的「爆紅」。尤其如果樣本本身都是小流量影片，中位數以上不代表爆紅；若樣本多是大頻道影片，中位數以下也可能有很高觀看數。

因此本專案建議把標籤拆成兩層：

1. `is_high_growth`：延續原提案，用於 baseline，比較容易取得平衡樣本。
2. `is_viral`：新的正式爆紅標籤，需考慮頻道規模、影片類型、分類與絕對觀看門檻。

### 12.2 預測時間設定

建議固定：

```text
observation_window = 發布後 0 到 3 小時
label_horizon = 發布後 24 小時
```

也就是：

- 模型只能看前 3 小時內能取得的資料。
- 標籤用 24 小時時的觀看表現決定。

若資料量足夠，可額外做 48 小時版本：

```text
is_viral_48h
```

但主實驗先以 `is_viral_24h` 為準，符合原提案中 24 小時成長分類的方向，也能在 2-3 週蒐集期內累積較多標籤。

### 12.3 為什麼不能只用絕對觀看數

只用 `views_24h >= 某數字` 會有問題：

- 大頻道天生曝光高，容易被標成爆紅。
- 小頻道即使成長超乎預期，也可能達不到絕對門檻。
- Shorts 與長片觀看分布不同，不能用同一門檻。
- 不同分類的自然流量差異大。

所以正式標籤應該是「相對於同類影片與頻道規模的異常高表現」，而不是單純觀看數大。

### 12.4 正式建議標籤：相對爆紅分數

定義 `viral_score_24h`：

```text
viral_score_24h = log1p(views_24h) - expected_log_views_24h
```

其中：

- `views_24h`：影片發布後 24 小時附近的觀看數。
- `expected_log_views_24h`：根據相似影片估計出的 24 小時預期觀看數。
- `log1p`：降低觀看數長尾偏斜。

`viral_score_24h` 的直覺：

- 大於 0：比相似影片預期更好。
- 等於 0：符合預期。
- 小於 0：低於預期。
- 約等於 `log(3)`：約為預期的 3 倍。

### 12.5 預期觀看數 baseline

`expected_log_views_24h` 不應用 validation/test 的資訊訓練，以免標籤規則間接看見測試分布。建議只用 training set 建立 baseline，再套用到 valid/test。

baseline 分層建議：

1. 先依 `is_shorts` 分開。
2. 再依 `category` 分層。
3. 再依 `subscriber_count` 分箱。
4. 可選擇性加入 `publish_hour_bucket`。

訂閱數分箱初始建議：

```text
[0, 1k)
[1k, 10k)
[10k, 100k)
[100k, 1M)
[1M, +inf)
```

發布時間分箱初始建議：

```text
0-5
6-11
12-17
18-23
```

若某分層樣本太少，使用 fallback：

1. `is_shorts + category + subscriber_bin + publish_hour_bucket`
2. `is_shorts + category + subscriber_bin`
3. `is_shorts + subscriber_bin`
4. `is_shorts`
5. 全訓練集 median

每層建議至少 `n >= 30`；若不足就往上 fallback。

### 12.6 `is_viral_24h` 二元標籤

正式建議：

```text
is_viral_24h = 1
if viral_score_24h >= log(3)
and views_24h >= min_abs_views_by_format
```

其中初始絕對門檻：

| 影片型態 | `min_abs_views_by_format` 初始值 | 理由 |
|---|---:|---|
| 長影片 | 1,000 views | 避免極小樣本因 baseline 過低被誤標爆紅 |
| Shorts | 5,000 views | Shorts 自然觀看數通常較高，門檻應較長片高 |

這些門檻不是寫死到永遠，而是第一版實驗的明確規格。若 EDA 顯示正負樣本嚴重失衡，可調整，但必須在報告中記錄調整前後的比例與理由。

### 12.7 邊界樣本處理

為了提升訓練標籤品質，可定義模糊區：

```text
log(2) <= viral_score_24h < log(3)
```

處理方式有兩種：

1. 課堂專題簡化版：全部標成 `0`，維持二元分類資料量。
2. 較嚴謹版本：從訓練集中排除模糊區，只在測試時保留並觀察模型分數。

若時間有限，建議採用第 1 種，並在報告中說明。

### 12.8 baseline 標籤：`is_high_growth_24h`

為了對照原提案，可保留中位數切分版本：

```text
growth_rate_24h = views_24h / max(views_3h, 1)
is_high_growth_24h = growth_rate_24h >= median(growth_rate_24h on training set)
```

注意：

- `is_high_growth_24h` 是高成長，不等同正式爆紅。
- median 必須只在 training set 算，再套到 valid/test。
- 報告時若使用這個標籤，應避免直接稱為爆紅。

### 12.9 最終建議輸出欄位

`data/processed/label_dataset.csv` 至少包含：

| 欄位 | 說明 |
|---|---|
| `video_id` | 影片 ID |
| `is_shorts` | 影片型態 |
| `category` | 分類 |
| `publish_time` | 發布時間 |
| `views_3h` | 3 小時觀看數 |
| `views_24h` | 24 小時觀看數 |
| `subscriber_count_at_publish` | 發布附近訂閱數 |
| `subscriber_bin` | 訂閱數分箱 |
| `expected_log_views_24h` | training baseline 估計值 |
| `viral_score_24h` | 相對爆紅分數 |
| `is_viral_24h` | 正式爆紅標籤 |
| `growth_rate_24h` | baseline 成長率 |
| `is_high_growth_24h` | 原提案式高成長標籤 |

## 13. 模型設計

最終簡報列出四種模型。

### 13.1 Logistic Regression

角色：線性基準模型。

目的：

- 確認非線性模型是否真的帶來增益。
- 作為 stacking 的 meta-learner。
- 提供最容易解釋的 baseline。

輸入：

- 表格特徵。
- 類別欄位需 one-hot encoding 或其他編碼。

### 13.2 LightGBM

角色：表格資料主力模型。

適合原因：

- 對結構化資料表現通常穩定。
- 訓練速度快。
- 可處理非線性與特徵交互。
- 可搭配 SHAP 做特徵解釋。

輸入：

- 12 個表格特徵。
- 可加入 Valence-Arousal 擴充特徵。

### 13.3 LSTM

角色：時序模型。

架構建議：

```text
2-layer LSTM
Dropout
Fully Connected output
Sigmoid probability
BCELoss 或 BCEWithLogitsLoss
```

輸入：

```text
T x 3 = (view_count, like_count, comment_count)
```

目的：

- 捕捉成長加速度。
- 捕捉爆發點。
- 捕捉平台期。
- 補足人工表格特徵不足之處。

### 13.4 Stacking Ensemble

角色：整合 LightGBM 與 LSTM。

最終簡報第 17 頁架構：

```text
表格特徵（12 個） -> LightGBM -> P1
時序輸入（T x 3） -> LSTM -> P2
P1, P2 -> Logistic Regression -> 最終預測
```

重點：

- LightGBM 抓靜態、頻道、早期摘要與留言特徵。
- LSTM 抓原始時間序列動態。
- Logistic Regression 作為 meta-learner 學習如何加權兩者。

實作注意：

- stacking 必須使用 out-of-fold prediction 或 validation prediction，避免 meta-learner 直接看見 base learner 在訓練資料上的過度樂觀分數。
- valid/test 切分必須一致。

## 14. 評估方式

### 14.1 指標

最終簡報指定：

| 指標 | 角色 | 理由 |
|---|---|---|
| F1-score | 主要指標 | 同時兼顧 precision 與 recall |
| AUC-ROC | 輔助指標 | 衡量排序能力，不受分類門檻影響，便於跨模型比較 |

若使用正式 `is_viral_24h`，正樣本可能偏少，建議另外報：

- Precision
- Recall
- PR-AUC
- Confusion matrix
- Positive rate

但簡報主軸仍以 F1 與 AUC-ROC 為主。

### 14.2 資料切分

最終簡報要求依時間順序切分：

- 早期影片作為 train。
- 較晚影片作為 valid/test。

目的：

- 避免時序洩漏。
- 模擬真實情境：用過去資料預測未來影片。

建議：

```text
train: 前 70%
valid: 中間 15%
test: 最後 15%
```

實際比例可依資料量調整，但不能隨機打散後切分作為主結果。

### 14.3 對照實驗

最終簡報第 24 頁定義三組：

| 組合 | 特徵 |
|---|---|
| A | 影片基本特徵 + 頻道特徵 |
| B | A + 早期流量特徵（含 LSTM 時序輸入） |
| C | B + 留言情緒特徵（完整版本） |

加入 Valence-Arousal 後，建議擴充為：

| 組合 | 特徵 | 目的 |
|---|---|---|
| A | 影片基本 + 頻道 | 最小可解釋 baseline |
| B | A + 早期流量 | 驗證 early signal 的價值 |
| C1 | B + binary sentiment | 對齊原提案 |
| C2 | B + Valence-Arousal | 回應老師回饋 |
| C3 | B + binary sentiment + Valence-Arousal | 完整留言情緒版本 |

若時間不足，至少保留 A、B、C2。

## 15. 預期成果

最終簡報列出的預期成果：

1. 可重複的 YouTube 爬蟲流程，包含 Shorts 判定。
2. 特徵集與 LSTM 時序資料兩套處理流程。
3. 四模型效能比較：LR / LGB / LSTM / Stack。
4. 對照實驗：量化各類特徵的邊際貢獻。
5. SHAP 特徵重要性分析，找出關鍵因素。

這五項應該對應到最終報告中的章節或結果圖表。

## 16. 時程規劃

最終簡報第 26 頁時程：

| 時間 | 項目 |
|---|---|
| 4 月 | 爬蟲架構 |
| 5 月上旬 | 資料蒐集 |
| 5 月中旬 | 清理與特徵 |
| 5 月下旬 | 模型訓練 |
| 6 月上旬 | 評估與報告 |

實作時可拆成更細：

1. 完成 repo 架構與設定。
2. 完成影片清單蒐集。
3. 完成 Shorts 判定。
4. 完成靜態資訊爬蟲。
5. 完成時序流量爬蟲與排程。
6. 完成留言爬蟲。
7. 完成情緒與 Valence-Arousal 特徵。
8. 完成 label dataset。
9. 完成 LightGBM baseline。
10. 完成 LSTM baseline。
11. 完成 stacking。
12. 完成 SHAP 與對照實驗圖表。

## 17. 最終簡報逐頁重點

此段保留最終 PDF 的頁面脈絡，方便之後撰寫 final report 或 README。

| 頁 | 主題 | 重點 |
|---:|---|---|
| 1 | 封面 | 題目、課程、組員 |
| 2 | 大綱 | 研究動機、研究資料、分析方式、方法、特色、評估、成果 |
| 3 | 研究動機分隔頁 | 進入第一章 |
| 4 | 動機 | YouTube 最大創作者舞台；早期表現決定流量；缺乏開放分析工具 |
| 5 | 核心問題與目標 | 用公開資料、早期流量、留言互動預測觀看數成長 |
| 6 | 研究資料分隔頁 | 進入第二章 |
| 7 | 資料來源與三大類別 | Python 爬蟲；STATIC / TIME / COMMENT |
| 8 | 欄位一覽 | 靜態、時序、留言欄位 |
| 9 | Shorts 判定 | HTTP GET `/shorts/{id}`；303 長片，200 Shorts |
| 10 | 分析方式分隔頁 | 進入第三章 |
| 11 | 分析流程 | 蒐集、清理、特徵、模型、解釋 |
| 12 | 表格特徵 | 共 12 個：影片基本、頻道、早期流量、留言情緒 |
| 13 | LSTM 輸入 | `T x 3`，前 3 小時，18-36 步 |
| 14 | 留言情緒 | RoBERTa 中文情緒模型，前 200 則留言，輸出平均分數 |
| 15 | 方法分隔頁 | 進入第四章 |
| 16 | 四種模型 | LR、LightGBM、LSTM、Stacking |
| 17 | Stacking | LightGBM 輸出 P1，LSTM 輸出 P2，LR meta-learner |
| 18 | 特色分隔頁 | 進入第五章 |
| 19 | 四大特色 | Shorts 判定、Stacking、留言降維、對照實驗 |
| 20 | 特色強調 | Shorts 判定 |
| 21 | 特色強調 | Shorts 判定 |
| 22 | 四大特色完整版 | 四項特色完整列出 |
| 23 | 評估分隔頁 | 進入第六章 |
| 24 | 評估與對照 | F1、AUC-ROC、A/B/C 對照、時間順序切分 |
| 25 | 預期成果分隔頁 | 進入第七章 |
| 26 | 成果與時程 | 五項成果與 4-6 月時程 |
| 27 | Q&A | 提案重點總結：二元分類、自行爬蟲、12 特徵 + LSTM、四模型、F1/AUC |

## 18. 方法特色與創新性整理

最終簡報的四大特色：

1. HTTP 狀態碼自動判定 Shorts：不需 API key，一行請求自動分流，分開建模消除雜訊。
2. 表格 ML + 時序 DL 的 Stacking：LightGBM 與 LSTM 捕捉互補資訊，比單一模型更穩定。
3. 留言特徵少而精路線：開源預訓練模型生成情緒分數，收斂成少數高層次指標。
4. 分階段對照實驗：量化靜態特徵、早期流量、留言情緒各自的貢獻。

加入老師回饋後，第三點應升級為：

> 留言情緒特徵從 binary sentiment 擴充為 Valence-Arousal，使模型同時看到情緒正負與情緒強度，並以少數高層次統計量保留可解釋性。

## 19. 實作時的最小可行版本

若時間有限，最小可行版本應完成：

1. 影片清單與靜態資料。
2. Shorts 判定。
3. 前 3 小時時序流量爬取。
4. 24 小時觀看數標籤。
5. `is_high_growth_24h` baseline 標籤。
6. `is_viral_24h` 正式標籤第一版。
7. 12 個表格特徵。
8. LightGBM。
9. F1 / AUC-ROC。
10. A/B/C 對照實驗。

如果還有時間，再補：

1. LSTM。
2. Stacking。
3. Valence-Arousal 完整特徵。
4. SHAP。
5. 48 小時標籤。

## 20. 重要風險與應對

### 20.1 資料量不足

風險：2-3 週資料可能不足以訓練穩定 LSTM 或細分 Shorts/長片。

應對：

- LightGBM 作為主要模型。
- LSTM 作為加分模型或小型 baseline。
- Shorts 與長片若分開後樣本太少，可先分層評估，再嘗試加入 `is_shorts` 作為特徵。

### 20.2 爆紅正樣本過少

風險：正式 `is_viral_24h` 可能正樣本很少。

應對：

- 同時保留 `is_high_growth_24h`。
- 調整 `log(3)` 門檻並記錄正樣本比例。
- 報告 PR-AUC、precision、recall。
- 使用 class weight 或 threshold tuning。

### 20.3 YouTube 前端改版

風險：爬蟲或 Shorts 判定規則失效。

應對：

- 保存原始 response status 與錯誤原因。
- 實作 retry。
- 保留未知狀態。
- 實作 fallback 判定。

### 20.4 留言特徵取得不穩

風險：新影片前 3 小時留言數很少，或留言載入不穩定。

應對：

- 加入 `comment_count_observed`。
- 加入 `has_comments_early`。
- 區分「沒有留言」與「未爬到留言」。
- 將留言特徵作為 C 組對照，不讓它阻塞 A/B baseline。

### 20.5 資料洩漏

風險：用到 24 小時後才知道的資訊訓練模型。

應對：

- 所有 feature 必須只來自 observation window。
- label 可使用 horizon window。
- split 必須時間順序切分。
- baseline threshold 與 viral expected baseline 必須只從 training set 估計。

## 21. 建議 repo 實作模組

後續程式碼可依下列模組拆分：

```text
src/
├── crawler/
│   ├── collect_video_list.py
│   ├── fetch_static.py
│   ├── fetch_timeseries.py
│   ├── fetch_comments.py
│   └── detect_shorts.py
├── preprocessing/
│   ├── clean_timeseries.py
│   ├── build_labels.py
│   ├── build_tabular_features.py
│   ├── build_sequences.py
│   └── build_comment_emotion_features.py
├── modeling/
│   ├── train_logistic.py
│   ├── train_lightgbm.py
│   ├── train_lstm.py
│   ├── train_stacking.py
│   └── evaluate.py
└── utils/
    ├── io.py
    ├── time.py
    └── logging.py
```

## 22. 最終報告可回答的問題

最終成果應至少回答：

1. 只看影片基本與頻道資訊，能不能預測高成長或爆紅？
2. 加入早期流量後，F1 / AUC 是否提升？
3. 加入留言情緒後，是否有額外提升？
4. Valence-Arousal 是否比單一 sentiment score 更有幫助？
5. LightGBM 與 LSTM 哪個表現較好？
6. Stacking 是否比單一模型穩定？
7. 哪些 feature 對模型最重要？
8. Shorts 與長片的模型表現是否不同？
9. 使用正式 `is_viral_24h` 與 baseline `is_high_growth_24h` 時，結論是否一致？

## 23. 專案成功標準

此專案不需要做到商業級預測系統才算成功。對資料探勘導論期末專題而言，成功標準是：

- 有清楚的研究問題。
- 有可重複的資料蒐集與前處理流程。
- 有明確且合理的標籤定義。
- 有對應研究問題的 feature design。
- 有 baseline 與較進階模型比較。
- 有正確的評估方式。
- 有對照實驗支撐結論。
- 有可解釋的分析結果。
- 能誠實說明限制與未來改進方向。

## 24. 當前最重要 TODO

依老師回饋與提案內容，接下來優先順序：

1. 實作或確認 `is_viral_24h` 標籤定義。
2. 實作 `is_high_growth_24h` baseline 標籤。
3. 確認 observation window 與 label horizon，避免資料洩漏。
4. 完成 Shorts 判定並驗證 303/200 規則仍可用。
5. 建立 raw / processed / split 資料架構。
6. 完成 12 個表格特徵。
7. 決定 Valence-Arousal 的模型或近似方法。
8. 完成 LightGBM baseline。
9. 視資料量完成 LSTM 與 stacking。
10. 完成 A/B/C 或 A/B/C1/C2/C3 對照實驗。

