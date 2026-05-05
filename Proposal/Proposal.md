# YouTube 影片流量預測與留言互動特徵分析

## 資料探勘導論期末專題提案報告

---

## 一、研究動機與目的

YouTube 是當前最具影響力的影音平台之一。對創作者而言，影片發布後的觀看數成長速度、按讚數與留言互動率，會直接影響影片能否被更多觀眾看見。若能在影片發布早期，根據影片本身資訊與初期互動數據預測後續流量變化，將有助於理解哪些因素與影片擴散有關。

本研究的核心問題為：**能否透過影片公開資料、早期流量變化與留言互動特徵，預測 YouTube 影片在未來一段時間內的觀看數成長表現。**

研究目標：

1. 建立 YouTube 影片資料蒐集流程，取得影片靜態資訊、時間序列流量資料與留言資料。
2. 設計可實際取得且具有分析意義的特徵。
3. 建立多種預測模型，比較不同類型方法（表格式機器學習與時間序列深度學習）對流量分類的效能。
4. 分析哪些特徵對流量預測較有幫助，特別是留言情緒特徵是否能提升模型表現。

---

## 二、研究資料

本研究資料由自行撰寫之 Python 爬蟲程式蒐集，資料來源為 YouTube 公開頁面可取得之資訊。所有資料以 JSON、CSV、JSONL 等文字檔案儲存，便於以 Pandas 處理。

### 2.1 影片靜態資料

以 JSON 儲存，`video_id` 為 key。欄位：

- `video_id`：影片唯一識別碼
- `title`：影片標題（用於計算 `title_length`）
- `channel_id`：頻道識別碼（用於爬取頻道訂閱數）
- `publish_time`：發布時間（用於計算 `publish_hour`）
- `duration_seconds`：影片長度（秒）
- `category`：影片分類
- `tag_count`：標籤數量（爬取時直接計數，反映標題 SEO 積極度）
- `is_shorts`：是否為 Shorts 短影片（判定方式見 4.1）

### 2.2 時間序列流量資料

以 CSV 長表格式儲存，每列代表一部影片在某時間點的狀態。欄位：

- `video_id`、`crawl_time`、`time_since_publish_minutes`
- `view_count`、`like_count`、`comment_count`（LSTM 時序輸入與衍生特徵來源）
- `subscriber_count`：頻道訂閱數（用於計算 `log_subscriber_count`）
- `video_status`：影片狀態（用於過濾不可用影片）

### 2.3 留言資料

每部影片獨立儲存為 JSONL 檔案。欄位：

- `video_id`、`comment_id`（去重用）
- `comment_text`：留言內容（情緒分析輸入）
- `comment_like_count`：留言按讚數（用於計算 `top_comment_like_ratio`）
- `crawl_time`

---

## 三、資料儲存架構

```text
youtube_traffic_project/
├── data/
│   ├── raw/
│   │   ├── static/videos_static.json
│   │   ├── timeseries/video_stats_all.csv
│   │   └── comments/by_video/{video_id}.jsonl
│   ├── processed/
│   │   ├── tabular_features.csv      # LightGBM 用
│   │   ├── sequences/                # LSTM 用，每部影片一個 npy
│   │   └── label_dataset.csv
│   └── split/{train,valid,test}.csv
├── src/{crawler,preprocessing,modeling,utils}/
├── models/
└── results/
```

靜態資料用 JSON 因查詢頻繁、key-value 結構自然；時序資料用 CSV 長表因 Pandas groupby 操作直接；留言用 JSONL 因逐行讀取可避免記憶體壓力。

---

## 四、分析方式

### 4.1 資料蒐集

**建立影片清單**：來源包含發燒影片、搜尋結果與指定頻道近期影片。每部新影片加入清單時，透過以下方式判定是否為 Shorts：對 `https://www.youtube.com/shorts/{video_id}` 發送 HTTP 請求（不跟隨重新導向），回傳 303 See Other 為長影片，回傳 200 OK 為 Shorts，並記入 `is_shorts`。此方法不需 API key，可自動標記。

由於 Shorts 與長片在演算法推送與流量行為上差異極大，本研究分開建模以避免混合雜訊。

**定期爬取流量**：每 **5–10 分鐘**更新一次觀看數、按讚數、留言數與訂閱數（間隔縮短以提供更密集的時序輸入給 LSTM）。

**定期爬取留言**：每 2 小時抓取一次，每部影片保留前 200 則熱門留言。

### 4.2 資料清理

- 同時間點重複資料保留最新一筆。
- 時序中間少數缺失以線性插補；整段缺失則排除該影片。
- 影片被刪除或轉為私人則不納入訓練。
- 觀看數使用 `log1p` 轉換以降低長尾偏斜。
- Shorts 與長影片分成兩個獨立資料集，分別建模。

### 4.3 特徵設計

特徵分為兩套：給 LightGBM 使用的**表格特徵**，與給 LSTM 使用的**時間序列輸入**。

**表格特徵（供 LightGBM，共 12 個）**

| 類別 | 特徵 | 為什麼用 |
|---|---|---|
| 影片基本 | `duration_seconds` | 長度影響觀看完成率與推薦行為 |
| | `category` | 不同分類流量分布差異大 |
| | `publish_hour` | 發布時段影響初期曝光 |
| | `is_shorts` | Shorts 與長片演算法行為截然不同 |
| | `title_length` | 反映標題資訊量，與點擊率相關 |
| | `tag_count` | 標籤數量反映創作者的 SEO 積極程度 |
| 頻道 | `log_subscriber_count` | 訂閱規模是初始曝光最強控制變項；取 log 因分布偏斜 |
| 早期流量 | `view_growth_rate_1h` | 首小時成長率是後續擴散最直接的訊號 |
| | `engagement_rate_early` | (likes+comments)/views，反映觀眾互動強度 |
| | `views_per_minute_early` | 初期速度，與訂閱數規模解耦 |
| 留言 | `comment_sentiment_score` | 留言整體情緒傾向（開源模型輸出，見下方） |
| | `top_comment_like_ratio` | 最熱門留言按讚數 / 觀看數，反映是否有「神留言」帶動傳播 |

**時間序列輸入（供 LSTM）**

每部影片整理為長度 T 的序列，每個時間步包含 3 個特徵：`(view_count, like_count, comment_count)`，以各自最大值歸一化。T 取影片前 3 小時的爬取點（5-10 分鐘間隔，約 18–36 步）。LSTM 直接從原始序列中學習成長加速度、平台期等時序結構，不需人工轉換成成長率。

**留言情緒分析**

使用開源中文預訓練模型（**`uer/roberta-base-finetuned-jd-binary-chinese`**），對每部影片的 200 則留言批次推論，輸出各留言情緒正向機率（0–1），彙整為平均值（`comment_sentiment_score`）。選此模型因其已在中文評論語料微調、可離線執行、不依賴付費 API。

### 4.4 預測目標

設定為**二元分類任務**：依「發布後 24 小時觀看數成長率」分為高成長與低成長兩類，以樣本中位數為分界。

---

## 五、預計嘗試的方法

三種類型的模型，每種代表不同的歸納假設，互相比較才有意義：

### 5.1 基準模型：Logistic Regression

線性模型，作為比較基準，確認後續模型確實有非線性增益。輸入為表格特徵。

### 5.2 表格模型：LightGBM

梯度提升決策樹，適合結構化表格資料。選 LightGBM 因其訓練速度快、原生支援類別變項（`category`）、可輸出 SHAP 值供特徵解釋。輸入為完整表格特徵。

### 5.3 時間序列模型：LSTM

對時序輸入建模，捕捉成長加速度、爆發模式等表格特徵無法表達的時序結構。架構為 2 層 LSTM + Dropout + 全連接輸出層，以 BCELoss 訓練。輸入為 (T × 3) 的歸一化時序序列。

### 5.4 整合模型：Stacking Ensemble

以 LightGBM 與 LSTM 的預測機率作為 meta-features，以 Logistic Regression 作為 meta-learner 進行 stacking。兩個 base learner 捕捉互補資訊：LightGBM 掌握靜態特徵與早期互動，LSTM 掌握時序動態，meta-learner 學習如何加權兩者。

---

## 六、方法特色與創新性

1. **以 HTTP 狀態碼自動判定 Shorts 與長影片**：公開 API 不直接提供此標記，本方法無需 API key 即可自動判定，並對兩種型態分開建模以消除混合雜訊。
2. **表格模型與時序模型的 Stacking**：LightGBM 與 LSTM 捕捉互補資訊，stacking 整合兩者而非單純選一。
3. **留言特徵走「少而精」路線**：以開源預訓練模型生成情緒分數，並收斂為兩個高層次指標，避免維度災難。
4. **分階段特徵組合對照實驗**：量化靜態特徵、早期流量、留言情緒三類特徵各自對預測效能的邊際貢獻（見第七節）。

---

## 七、模型效能評估方式

| 指標 | 為什麼用 |
|---|---|
| **F1-score** | 主要指標。高低成長類別即使以中位數切分仍可能略有偏差，F1 同時兼顧 precision 與 recall |
| **AUC-ROC** | 衡量模型排序能力，不受分類門檻影響，便於跨模型比較 |

**資料切分**：依時間順序切分（早期影片為訓練集、晚期為測試集），避免時序洩漏。

**對照實驗**（回答「各類特徵是否有幫助」）：

| 組合 | 特徵 |
|---|---|
| A | 影片基本特徵 + 頻道特徵 |
| B | A + 早期流量特徵（含 LSTM 時序輸入） |
| C | B + 留言情緒特徵 |

各組合分別在 LightGBM、LSTM、Stacking 三個模型上跑，比較 F1 與 AUC 的差異，量化每類特徵的邊際貢獻。

---

## 八、預期成果

1. 建立可重複執行的 YouTube 資料蒐集流程，包含 Shorts 自動判定與高頻時序爬取。
2. 完成表格特徵集與 LSTM 時序輸入兩套資料處理流程。
3. 完成 Logistic Regression、LightGBM、LSTM、Stacking 四個模型的比較。
4. 透過對照實驗量化靜態特徵、早期流量特徵、留言情緒特徵各自的邊際貢獻。
5. 產出 SHAP 特徵重要性分析，找出影響影片成長的關鍵因素。

---

## 九、預定研究流程

1. 建立爬蟲與資料夾架構，實作 Shorts 判定邏輯。
2. 蒐集影片靜態資料與初步影片清單。
3. 定期蒐集時間序列流量資料（持續 2–3 週）。
4. 蒐集留言並以開源模型批次計算情緒分數。
5. 資料清理、表格特徵工程與 LSTM 時序資料整理。
6. 訓練模型、執行對照實驗、評估效能。
7. 撰寫期末報告與視覺化結果。

---

## 十、結論

本專題以 YouTube 影片流量預測為主題，透過公開可取得之影片資訊、高頻時間序列流量資料與留言互動資料，建立一套完整的資料探勘分析流程。方法設計同時包含表格式機器學習（LightGBM）與時間序列深度學習（LSTM），並以 Stacking 整合兩者的互補優勢。透過對照實驗可具體回答「留言情緒特徵是否能提升 YouTube 影片流量預測效能」這一核心問題。
