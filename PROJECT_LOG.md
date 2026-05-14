# PROJECT_LOG.md

資料探勘導論期末專案 — YouTube 影片爆紅預測。本檔紀錄爬蟲開發過程的設計決策、bug 修復、策略調整。
任務定義與資料規格見 `PROJECT_CONTEXT.md`。

---

## 1. 爬蟲架構概覽

主迴圈 `src/crawler/run_scheduler.py` 每 60 秒 tick 一次，依排程觸發：

| Job | 用途 | 目前狀態 |
|---|---|---|
| `fresh_search` | 搜尋「最近 1 小時上傳」並過濾 ≤5 min 的影片 | **唯一活躍的發現來源** |
| `shorts_page` | 搜尋 #shorts 取得新 Shorts | **活躍**（每 10 min）|
| `explore` | YouTube Explore 各分類熱門 | 已停用（`DISCOVERY_DISABLED=True`）|
| `search` | 一般關鍵字搜尋 | 已停用 |
| `channel` | 追蹤頻道輪詢 | 已停用 |
| `static` | 對新影片抓 metadata + comment count | 持續 |
| `timeseries` | 對追蹤中影片定期抓 view/like/comment | 持續，依年齡分段間隔 |
| `comments` | 0–3h 內抓 t1h/t2h/t3h 留言 snapshot | 持續 |

State 儲存在 `data/state.db`（SQLite），原始資料在 `data/raw/{static,timeseries,comments}/`。

---

## 2. YouTube API 變化的踩雷與修復

### 2.1 `/feed/trending` 已下架
YouTube 在 2025 年移除全站 trending。改用 Explore 分類頁（`/gaming`, `/news`, `/sports`, `/live`, `/podcasts`），每次每分類隨機取 3–5 部影片。

**後續調整**：發現 `/movies` 的影片全屬同一個「YouTube Movies」channel，`channel_id` 重複無分析意義，已從分類清單移除。

### 2.2 Atom RSS (`/feeds/videos.xml`) 回傳 404
原本用來取得 channel 最新上傳。改用 InnerTube：
```
POST /youtubei/v1/browse
{"browseId": channel_id, "params": "EgZ2aWRlb3PyBgQKAjoA"}
```
（`params` 是 Videos tab 的 base64-encoded protobuf。）

頻道頁 HTML 也試過，但已改用 `lockupViewModel` 格式（沒有 `videoId` 欄位），所以走 InnerTube 是必須的。

### 2.3 留言內容欄位搬家（ViewModel）
2024+ YouTube 把 comment 本文從 `commentRenderer` 搬到：
```
frameworkUpdates.entityBatchUpdate.mutations[].payload.commentEntityPayload.properties.content.content
```
原本只解析 `commentRenderer` 的程式碼會抓到空字串（comment_text 全空、comment_id 都重複）。

**修復**：`fetch_comments.py` 加入 `_extract_mutations()`，先把 mutations 抽成 `{commentId → {text, like_count, published_time}}` lookup table，再用 `commentViewModel.commentId` 對照填回。

### 2.4 `comment_published_at` 只能拿到相對時間
YouTube 沒給 comment 的絕對 timestamp，只給 `"6 個月前"`、`"3 分鐘前"` 這種字串。建模時若需要絕對時間，用 `crawl_time` 當代理值。

### 2.5 Shorts 來源
`/shorts` 首頁只展示單一影片（透過 `replacementEndpoint`），不能爬清單。改用 YouTube 搜尋 + `sp=EgQQARgD`（Shorts filter）+ `#shorts` 關鍵字。

---

## 3. 重大事故與根因修復

### 3.1 卡住的影片佔住 static fetch queue
**現象**：3 支影片（ElhmVbycbfM、PZGJQ_B4_64、lJ2czS33zM4）連續 200+ 次 `returned None`，每次跑 batch 都是它們，導致 927 部 pending 影片完全跑不到。

**根因**：`_run_static_fetches` 沒有失敗計數，永久重試。

**修復**：新增 `_mark_static_give_up_if_exhausted()` — 同一影片 fetch_static 累計 ≥3 次錯誤就把 `static_fetched=-1`（永久跳過）。已知卡住影片立即手動標記。

### 3.2 `videos_static.json` 損毀（雙 scheduler 互覆寫）
**現象**：`Extra data: line 71645 column 4 (char 1839322)`，2h 內 177 筆 static fail。

**根因**：`save_json_dict()` 用固定檔名 `videos_static.tmp`。當有兩個 scheduler process 同時跑時（早期 cron job 加上手動啟動造成），兩個 process 同時 truncate 並寫入同一個 tmp 檔，內容互相覆蓋，最後其中一個 `os.replace()` 把 corruption 結果搬到正式檔。

**修復**：
1. `src/utils/io.py` — tmp 檔名改為 `videos_static.{PID}.tmp`，process 互不干擾
2. 用 `json.JSONDecoder().raw_decode()` 把損毀檔拆成前段（有效）+ 後段碎片，merge 後寫回（救回 2081 筆）
3. 41 支因 JSON 解析錯誤而被誤判 `gave_up=-1` 的影片重置回 `static_fetched=0`

### 3.3 `_sleep` 負數造成 10 小時停擺
**現象**：scheduler crash with `ValueError: sleep length must be non-negative`，無人發現直到 10 小時後人工檢查。

**根因**：`http_client._sleep()` 的 race：
```python
while not _stop and time.monotonic() < end:        # check 時還沒過期
    time.sleep(min(0.5, end - time.monotonic()))   # 但這行已過期 → 負數
```

**修復**：先算 `remaining`，≤0 就 break：
```python
while not _stop:
    remaining = end - time.monotonic()
    if remaining <= 0: break
    time.sleep(min(0.5, remaining))
```

**後果**：那 10 小時內所有處於 0–3h 窗口的影片喪失早期高頻資料，無法用於分類任務。

### 3.4 兩個 scheduler 重複跑（cron job 副作用）
**現象**：發現 2 個 python.exe 跑同個 `run_scheduler`，是 3.2 事故的根本原因。

**根因**：稍早設定的「2h 健康檢查 cron job」會無條件執行 PowerShell 重啟腳本；該腳本用 `Get-Process python | Select-Object -First 1` 抓現有 process，但偶爾因 WMI 回應慢抓到 null，於是「沒抓到 → 沒 kill → 直接開新的」，最後兩個都跑。

**修復**：取消該 cron job（`CronDelete 0f42418d`），改成手動觸發健康檢查。重啟腳本也建議先 `if (-not (Get-Process python))` 檢查。

---

## 4. Timeseries 間隔策略演進

`schedule_next_timeseries()` 根據影片年齡決定下次抓取時間。歷次調整：

| 階段 | 0–3h | 3–48h | 48–72h | 72h+ |
|---|---|---|---|---|
| 初版 | 7 min | 60 min | 60 min | 360 min |
| 第一次調整 | **10 min** | **120 min** | 120 min | 360 min |
| 目前 | 10 min | 120 min | 120 min | 360 min |

### 4.1 飄移修復：從 `last_due` 排，不從 `now`
原本：`next_due = now + interval`，每次都從實際執行時刻算下一次 → 誤差累積。
改成：`next_due = max(last_due + interval, now)` → 誤差不累積，穩定後接近目標間隔。

實際間隔 = 設定值 + 0–60 秒（tick 等待）+ 0–60 秒（jitter sleep 和 batch 處理）。
**註**：不可能完全準時。10 分鐘間隔實際大約落在 10–12 分鐘。

### 4.2 容量計算
- 主迴圈每 tick 拿 batch=20 部影片做 timeseries → 理論上限 **1200 筆/小時**
- 設定 10/120/120/360 後，每部影片在 144h 生命週期內：3h/10min × 1 + 45h/2h × 1 + 24h/2h × 1 + 72h/6h × 1 = 約 64 個 snapshot

### 4.3 影片追蹤總長：6 天（144h）
原本 168h（7 天），改成 **144h = 兩個 72h 窗口**，給回歸任務多一個 fallback window 同時稍微減輕負擔。

---

## 5. 影片發現策略演進

| 階段 | 策略 |
|---|---|
| 初期 | trending（已下架）|
| v1 | Explore 6 分類 + search + channel hourly + shorts |
| v2 | 移除 movies；explore 從 3–5 部 → 1–2 部 |
| v3 | channel 輪詢從 60min → 10min；search 加入「today」filter |
| v4 | **fresh_search 用「last hour + sort=new」filter，本地再過濾到 ≤5 min 上傳的影片；停掉 explore/search/channel；shorts 每 10 min** |

### 5.1 v4 動機
回頭看資料品質，10,238 支影片中只有 **202** 部 0–3h + 48h 資料完整可供分類任務訓練（1.97%）。原因：影片被發現時平均已過 30+ 分鐘，0–3h 早期資料缺失。

新策略只接收「YouTube 顯示為 5 分鐘內上傳」的影片，並用 5 min 排程確保 fresh_search 高頻運作。

### 5.2 published_time_text 過濾
搜尋結果含 `"3 分鐘前"`、`"剛剛"`、`"30 秒前"` 等 zh-TW 相對時間字串。`_is_very_fresh()` 用正規式判斷：
- 含「剛剛」/「秒」→ 通過
- 含「N 分鐘前」且 N ≤ 5 → 通過
- 其他 → 丟棄

---

## 6. 程式碼結構變動摘要

| 檔案 | 主要變動 |
|---|---|
| `src/crawler/fetch_explore.py` | 新檔；取代 fetch_trending |
| `src/crawler/fetch_shorts_page.py` | 新檔；search-based Shorts 發現 |
| `src/crawler/fetch_channel_uploads.py` | RSS → InnerTube browse |
| `src/crawler/fetch_comments.py` | 加 `_extract_mutations()` 處理 ViewModel |
| `src/crawler/fetch_search.py` | 加 `sp` 參數和 `SP_LAST_HOUR_SORT_NEW` 常數 |
| `src/crawler/collect_video_list.py` | 加 `collect_from_fresh_search` + `_is_very_fresh` filter |
| `src/crawler/run_scheduler.py` | 重組 discovery 排程；加 `_mark_static_give_up_if_exhausted`；加 `DISCOVERY_DISABLED` flag |
| `src/utils/state_db.py` | `schedule_next_timeseries` 改用 `last_due`；`track_until` 改 144h |
| `src/utils/io.py` | `save_json_dict` 用 PID 區分 tmp 檔 |
| `src/utils/http_client.py` | 修 `_sleep` 負數 race |
| `tmp/test_crawlers.py` | 10 個爬蟲功能驗收測試（不入版控）|
| `.gitignore` | 加 `tmp/` |

---

## 7. 進度資料快照（2026-05-13）

- 爬蟲累計執行：~4.7 天（含一次 10h downtime）
- 影片總數：10,263 支（static_fetched=1）
- Shorts：382 支（3.7%）
- 有 timeseries 資料：6,798 支
- 追蹤時長分布：p25=36h, p50=59h, p75=93h, p90=130h, max=168h

| 任務 | 可用影片數 | 其中 Shorts | 備註 |
|---|---|---|---|
| 分類（0–3h + 48h 完整）| 202 | 12 | 受 10h downtime 重創 |
| 回歸（追蹤 ≥72h）| 2,682 | 87 | k=0 視窗 |
| 回歸 k-windows 總數（1h 步長）| 103,732 | 3,400 | 高度相關，不建議全用 |

---

## 8. 未解議題 / 後續可做

- [ ] **資料偏斜**：Shorts 佔比 3.7%，要做 shorts vs long-form 比較需要額外補爬
- [ ] **0–3h 完整資料稀缺**：依目前 v4 策略，新爬到的影片應該都會有完整 0–3h；舊資料用不了
- [ ] **comment_published_at 絕對時間**：YouTube 不開放，目前用 crawl_time 代理
- [ ] **WinError 5 / 32 偶發**：防毒軟體鎖檔，每輪 3–5 次失敗但會自動恢復，未修
- [ ] **健康檢查自動化**：原 cron job 已停，目前靠手動觸發
