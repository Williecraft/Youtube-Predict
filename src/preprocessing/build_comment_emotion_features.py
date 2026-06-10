"""
留言情緒特徵（Group C1 / C2 / C3）。

以 t3h snapshot 留言為主輸入，產出影片層級的情緒特徵：

Group C1（Binary Sentiment）
  comment_sentiment_score       — 正向分數平均（HuggingFace pipeline）
  top_comment_like_ratio        — like 最高前 5 則的正向比例
  comment_count_3h              — t3h snapshot 留言數

Group C2（Valence-Arousal proxy）
  comment_valence_mean          — sentiment_score 當 valence proxy
  comment_valence_std
  comment_arousal_mean          — arousal proxy（驚嘆號/emoji/強烈語氣詞比例）
  comment_arousal_std
  comment_high_arousal_ratio    — arousal >= 0.65 的比例

輸出：data/processed/comment_features.csv
      video_id + 8 個情緒特徵
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.load_raw import load_comments
from src.preprocessing.paths import (
    COMMENT_FEATURES_CSV,
    LABEL_DATASET_CSV,
    ensure_processed_dirs,
)

logger = logging.getLogger(__name__)

# ── arousal proxy 正則 ──────────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF]+",
    flags=re.UNICODE,
)
_INTENSE_RE = re.compile(
    r"[！!]{2,}|哇+|好棒|超讚|太強|真的嗎|OMG|omg|wow|WOW|amazing|awesome|"
    r"震驚|不敢相信|太厲害|神了|絕了|狂了|哈哈+|LOL|lol|XD|xd",
    flags=re.IGNORECASE,
)


def _arousal_score(text: str) -> float:
    """簡單的 arousal proxy：驚嘆號密度 + emoji 密度 + 強烈語氣詞存在。"""
    if not text or not isinstance(text, str):
        return 0.0
    n = max(len(text), 1)
    excl   = text.count("!") + text.count("！")
    emojis = len(_EMOJI_RE.findall(text))
    intense = 1 if _INTENSE_RE.search(text) else 0
    score = min(1.0, (excl / n * 10) + (emojis / n * 5) + intense * 0.3)
    return float(score)


def _build_features_with_hf(
    comments_df: pd.DataFrame,
    batch_size: int = 64,
) -> pd.DataFrame:
    """使用 HuggingFace pipeline 做 binary sentiment。"""
    try:
        from transformers import pipeline as hf_pipeline
        import torch
        device = 0 if torch.cuda.is_available() else -1
        logger.info("載入 sentiment model（device=%d）...", device)
        sentiment_pipe = hf_pipeline(
            "text-classification",
            model="uer/roberta-base-finetuned-jd-binary-chinese",
            device=device,
            truncation=True,
            max_length=128,
        )
    except Exception as e:
        logger.warning("HuggingFace pipeline 載入失敗 (%s)，改用 lexicon fallback", e)
        return _build_features_lexicon(comments_df)

    texts = comments_df["comment_text"].fillna("").tolist()
    scores: list[float] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        try:
            results = sentiment_pipe(batch)
            for r in results:
                # uer/roberta-base label: 'positive (stars 4 and 5)' / 'negative (stars 1, 2 and 3)'
                # 通用判斷：label 字串開頭含 'pos' 或 'LABEL_1' → 正向
                lbl = r["label"].lower()
                is_pos = lbl.startswith("pos") or lbl == "label_1"
                scores.append(r["score"] if is_pos else 1.0 - r["score"])
        except Exception:
            scores.extend([0.5] * len(batch))
        if (i // batch_size) % 20 == 0:
            logger.info("sentiment 進度 %d/%d", i, len(texts))

    comments_df = comments_df.copy()
    comments_df["sentiment_score"] = scores
    return comments_df


def _build_features_lexicon(comments_df: pd.DataFrame) -> pd.DataFrame:
    """Lexicon fallback：正向/負向詞典估算情緒分數。"""
    POS = {"好", "棒", "讚", "強", "厲害", "喜歡", "愛", "開心", "感謝",
           "great", "good", "love", "nice", "amazing", "awesome", "excellent"}
    NEG = {"差", "爛", "糟", "討厭", "垃圾", "失望", "難看", "boring",
           "bad", "terrible", "awful", "hate", "worst"}

    def _lex_score(text: str) -> float:
        if not text or not isinstance(text, str):
            return 0.5
        t = text.lower()
        pos = sum(1 for w in POS if w in t)
        neg = sum(1 for w in NEG if w in t)
        if pos + neg == 0:
            return 0.5
        return pos / (pos + neg)

    comments_df = comments_df.copy()
    comments_df["sentiment_score"] = comments_df["comment_text"].map(_lex_score)
    return comments_df


def _aggregate_per_video(comments_df: pd.DataFrame) -> pd.DataFrame:
    """彙整留言情緒分數到影片層級。"""
    HIGH_AROUSAL_THRESH = 0.65

    records = []
    for vid, grp in comments_df.groupby("video_id"):
        sent = grp["sentiment_score"].values
        arousal = grp["arousal_score"].values

        # 取按 like 數排序前 5 則的正向比例
        top5 = grp.nlargest(5, "comment_like_count") if "comment_like_count" in grp.columns else grp.head(5)
        top5_pos_ratio = float((top5["sentiment_score"] > 0.5).mean()) if len(top5) > 0 else 0.5

        records.append({
            "video_id": vid,
            # C1
            "comment_sentiment_score": float(np.mean(sent)) if len(sent) > 0 else 0.5,
            "top_comment_like_ratio":  top5_pos_ratio,
            "comment_count_3h":        len(grp),
            # C2 (valence = sentiment proxy, arousal = arousal proxy)
            "comment_valence_mean":    float(np.mean(sent)) if len(sent) > 0 else 0.5,
            "comment_valence_std":     float(np.std(sent)) if len(sent) > 0 else 0.0,
            "comment_arousal_mean":    float(np.mean(arousal)) if len(arousal) > 0 else 0.0,
            "comment_arousal_std":     float(np.std(arousal)) if len(arousal) > 0 else 0.0,
            "comment_high_arousal_ratio": float((arousal >= HIGH_AROUSAL_THRESH).mean()) if len(arousal) > 0 else 0.0,
        })

    return pd.DataFrame.from_records(records)


def build_comment_features(video_ids: list[str] | None = None) -> pd.DataFrame:
    """
    主函式：載入留言 → 跑 sentiment → 計算 arousal proxy → 彙整 → 回傳 DataFrame。

    video_ids 若為 None，自動從 label_dataset.csv 取。
    """
    if video_ids is None and LABEL_DATASET_CSV.exists():
        video_ids = pd.read_csv(LABEL_DATASET_CSV, usecols=["video_id"])["video_id"].tolist()

    comments = load_comments(video_ids=video_ids)
    if comments.empty:
        logger.warning("沒有留言資料，回傳空 DataFrame")
        return pd.DataFrame()

    # 只用 t3h snapshot（最完整）
    t3h = comments[comments["snapshot_label"] == "t3h"].copy()
    if t3h.empty:
        logger.warning("t3h snapshot 為空，改用所有 snapshot")
        t3h = comments.copy()

    logger.info("載入 %d 則留言（%d 部影片）", len(t3h), t3h["video_id"].nunique())

    # sentiment
    t3h = _build_features_with_hf(t3h)

    # arousal proxy
    t3h["arousal_score"] = t3h["comment_text"].fillna("").map(_arousal_score)

    # 彙整
    feat_df = _aggregate_per_video(t3h)
    logger.info("comment_features 完成：%d 部影片", len(feat_df))
    return feat_df


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_processed_dirs()
    df = build_comment_features()
    if df.empty:
        logger.warning("comment_features 為空，不寫入檔案")
        return
    df.to_csv(COMMENT_FEATURES_CSV, index=False)
    logger.info("comment_features 寫入 %s（%d 部影片）", COMMENT_FEATURES_CSV, len(df))


if __name__ == "__main__":
    main()
