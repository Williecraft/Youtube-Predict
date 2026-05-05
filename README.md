# YouTube 影片流量預測與留言互動特徵分析

資料探勘導論期末專題。此專案目標是透過 YouTube 影片公開資料、發布早期流量變化、留言互動與情緒特徵，預測影片後續是否會出現高成長或爆紅表現。

詳細研究規格、資料欄位、模型設計、老師回饋與爆紅標籤定義請見 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)。

## 專案重點

- 自行撰寫 Python 爬蟲蒐集 YouTube 公開資料。
- 蒐集三類資料：影片靜態資訊、時序流量資料、留言資料。
- 使用 HTTP 狀態碼自動判定 Shorts 與長影片，並分開建模以降低雜訊。
- 設計 12 個表格特徵，涵蓋影片基本資訊、頻道規模、早期流量與留言情緒。
- 使用 LSTM 處理發布後前 3 小時的觀看數、按讚數、留言數時間序列。
- 比較 Logistic Regression、LightGBM、LSTM 與 Stacking Ensemble。
- 使用 F1-score 與 AUC-ROC 評估模型效果。
- 加入老師提到的 Valence-Arousal 作為進階情緒特徵方向。
- 定義穩定明確的 `is_viral_48h` 爆紅標籤，避免只用模糊的觀看數高低分類。

## 研究問題

核心問題：

> 能否透過影片公開資料、早期流量與留言互動特徵，預測 YouTube 影片的觀看數成長表現？

實作上會將問題轉成二元分類任務：

- 輸入：影片發布後早期可取得的資料。
- 輸出：影片是否達到高成長或爆紅標準。
- 主要預測時間窗：使用發布後前 3 小時資料，預測發布後 48 小時表現。

## 資料類型

| 類型 | 格式 | 內容 |
|---|---|---|
| 靜態資訊 | JSON | `video_id`、標題、頻道、發布時間、影片長度、分類、標籤數、是否 Shorts |
| 時序流量 | CSV | 爬取時間、距發布時間、觀看數、按讚數、留言數、訂閱數、影片狀態 |
| 留言資料 | JSONL | 留言 ID、留言文字、留言按讚數、爬取時間 |

## 預計方法

| 模型 | 角色 |
|---|---|
| Logistic Regression | 線性基準模型 |
| LightGBM | 表格特徵主力模型，並支援 SHAP 解釋 |
| LSTM | 時序模型，捕捉成長加速度、爆發點與平台期 |
| Stacking Ensemble | 整合 LightGBM 與 LSTM 的預測機率 |

## 評估設計

主要評估指標：

- F1-score
- AUC-ROC

對照實驗：

| 組合 | 特徵 |
|---|---|
| A | 影片基本特徵 + 頻道特徵 |
| B | A + 早期流量特徵 |
| C | B + 留言情緒特徵 |

後續可擴充比較 binary sentiment 與 Valence-Arousal 情緒特徵的效果。

## 專案文件

- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)：完整專案說明書與實作規格。
- [Proposal/YouTube_Prediction_Final.pptx.pdf](Proposal/YouTube_Prediction_Final.pptx.pdf)：期中提案最終簡報 PDF。
- [Proposal/Proposal.md](Proposal/Proposal.md)：提案文字版。
- [Proposal/Proposal_requirements.txt](Proposal/Proposal_requirements.txt)：課程提案要求。

若 `Proposal.md` 與最終簡報 PDF 有衝突，以最終簡報 PDF 為準。

## 預期成果

1. 可重複執行的 YouTube 資料蒐集流程。
2. Shorts 與長影片自動判定。
3. 表格特徵集與 LSTM 時序資料集。
4. 四種模型的效能比較。
5. 分階段對照實驗結果。
6. SHAP 特徵重要性分析。
7. 明確可追蹤的爆紅標籤定義。

## 專案狀態

目前為提案與規格整理階段，已完成最終提案文件整理與專案 context 撰寫。後續重點是建立資料蒐集、前處理、標籤生成與模型訓練流程。
