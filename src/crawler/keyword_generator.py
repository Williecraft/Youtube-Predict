"""
關鍵字產生器
產生 YouTube 搜尋關鍵字，供 fetch_search.py 使用。

兩個來源：
  (a) 種子組合池：人工分類欄位隨機拼接（70%）
  (b) Trending tags 動態池：從發燒影片 tags 欄位抽取（30%）

使用方式：
  單獨驗收：python -m src.crawler.keyword_generator --n 50
  取得關鍵字：from src.crawler.keyword_generator import generate_keywords
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
import json

# ── (a) 種子組合池 ─────────────────────────────────────────────────────────

MODIFIERS = [
    "最新", "2026", "推薦", "精選", "必看", "爆笑", "感人", "超狂",
    "台灣", "日本", "韓國", "歐美", "地下", "冷門", "超夯",
]

TOPICS = [
    "美食", "旅遊", "遊戲", "電影", "動漫", "韓劇", "日劇", "台劇",
    "健身", "投資理財", "AI", "科技", "寵物", "育兒", "時事", "政治",
    "音樂", "搞笑", "vlog", "街訪", "開箱", "挑戰", "實驗",
    "考試", "學習", "語言", "程式設計", "攝影", "美妝", "穿搭",
    "籃球", "足球", "棒球", "電競", "料理", "甜點", "咖啡",
]

FORMATS = [
    "vlog", "教學", "實測", "評測", "反應", "排行榜",
    "ASMR", "短片", "採訪", "紀錄片", "ft.", "",
    "開箱", "試吃", "挑戰", "攻略",
]


def _seed_keyword() -> str:
    """從種子欄位隨機組合 1–3 個詞。"""
    n = random.choices([1, 2, 3], weights=[2, 5, 3])[0]
    parts: list[str] = []

    pools_by_slots = {
        1: [TOPICS],
        2: random.choice([
            [MODIFIERS, TOPICS],
            [TOPICS, FORMATS],
        ]),
        3: [MODIFIERS, TOPICS, FORMATS],
    }

    for pool in pools_by_slots[n]:
        word = random.choice(pool)
        if word:
            parts.append(word)

    return " ".join(parts).strip()


# ── (b) Trending tags 動態池 ──────────────────────────────────────────────

def _load_trending_tags(static_path: Path) -> list[str]:
    """
    從 videos_static.json 收集最近發燒影片的 tags。
    檔案不存在或為空時回傳空 list（fallback 到種子池）。
    """
    if not static_path.exists():
        return []
    try:
        data: dict = json.loads(static_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    tags: list[str] = []
    for entry in data.values():
        tags.extend(entry.get("tags", []) or [])
    # 去空白、去重
    return list({t.strip() for t in tags if isinstance(t, str) and t.strip()})


def _trending_keyword(trending_tags: list[str]) -> str | None:
    """從 trending tag 池隨機抽 1–2 個，組成關鍵字。若 pool 空回 None。"""
    if not trending_tags:
        return None
    n = random.choices([1, 2], weights=[3, 2])[0]
    picked = random.sample(trending_tags, min(n, len(trending_tags)))
    return " ".join(picked)


# ── 公開介面 ──────────────────────────────────────────────────────────────

def generate_keywords(
    n: int = 7,
    trending_tags: list[str] | None = None,
    trending_ratio: float = 0.3,
) -> list[str]:
    """
    產生 n 個搜尋關鍵字。

    Parameters
    ----------
    n : int
        要產生的關鍵字數量（通常 5–7）。
    trending_tags : list[str] | None
        從發燒影片 tags 欄位收集的 tag pool；None 表示全用種子池。
    trending_ratio : float
        trending pool 佔的比例（預設 30%）。
    """
    results: list[str] = []
    tags = trending_tags or []

    for _ in range(n):
        use_trending = tags and random.random() < trending_ratio
        if use_trending:
            kw = _trending_keyword(tags)
            if kw:
                results.append(kw)
                continue
        results.append(_seed_keyword())

    return results


# ── CLI 驗收入口 ──────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(description="生成並列印 n 個搜尋關鍵字")
    parser.add_argument("--n", type=int, default=50, help="產生數量")
    parser.add_argument(
        "--static",
        type=Path,
        default=Path("data/raw/static/videos_static.json"),
        help="videos_static.json 路徑（用來載入 trending tags）",
    )
    parser.add_argument("--seed", type=int, default=None, help="固定亂數種子（可重現）")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    trending_tags = _load_trending_tags(args.static)
    keywords = generate_keywords(args.n, trending_tags)

    print(f"生成 {len(keywords)} 個關鍵字（trending_tags pool 大小：{len(trending_tags)}）\n")
    for i, kw in enumerate(keywords, 1):
        print(f"  {i:>3}. {kw}")


if __name__ == "__main__":
    _main()
