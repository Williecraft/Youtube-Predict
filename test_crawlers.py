"""
快速功能測試，跑完會自動清掉產生的檔案。
用法：python test_crawlers.py
"""

import logging
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT))

from src.utils.http_client import YouTubeClient
from src.utils.logging import setup_file_logging

_log_dir = ROOT / "logs"
setup_file_logging(_log_dir, "test.log")

client = YouTubeClient()

_PASS = "✓"
_FAIL = "✗"
results = []

# 已知影片作為 fallback（確保後續測試能跑）
_FALLBACK_VIDEO_ID   = "jNQXAC9IVRw"   # Me at the zoo（第一支 YouTube 影片，公開、長影片）
_FALLBACK_CHANNEL_ID = "UC4QobU6STFB0P71PMvOGN5A"  # jawed（Me at the zoo 上傳者）


def check(name, fn):
    try:
        val = fn()
        ok = bool(val)
        tag = _PASS if ok else _FAIL
        note = repr(val)[:120] if not ok else ""
        print(f"  {tag}  {name}" + (f"\n       ↳ {note}" if note else ""))
        results.append((name, ok))
        return val
    except Exception:
        print(f"  {_FAIL}  {name}")
        traceback.print_exc(limit=3)
        results.append((name, False))
        return None


# ── 1. trending ────────────────────────────────────────────────────────────
print("\n[1] fetch_trending (TW only)")
from src.crawler.fetch_trending import fetch_trending, _fetch_region
from src.utils.http_client import extract_js_var

# 先看 GET 能不能拿到頁面
resp = client.get("https://www.youtube.com/feed/trending", params={"gl": "TW", "hl": "zh-TW"})
got_page = resp is not None and resp.status_code == 200
print(f"  {'✓' if got_page else '✗'}  GET /feed/trending status={resp.status_code if resp else 'None'}")

if got_page:
    data = extract_js_var(resp.text, "ytInitialData")
    has_data = bool(data)
    print(f"  {'✓' if has_data else '✗'}  ytInitialData 解析{'成功' if has_data else '失敗（頁面結構可能改變）'}")

trending = check("trending 至少拿到 1 部影片", lambda: fetch_trending(client, regions=["TW"]))
test_video_id   = _FALLBACK_VIDEO_ID
test_channel_id = _FALLBACK_CHANNEL_ID
if trending:
    test_video_id   = trending[0]["video_id"]
    test_channel_id = trending[0].get("channel_id") or _FALLBACK_CHANNEL_ID
    print(f"       ↳ 共 {len(trending)} 部，測試用 video_id={test_video_id}")
else:
    print(f"       ↳ trending 失敗，用 fallback video_id={test_video_id}")

# ── 2. search ──────────────────────────────────────────────────────────────
print("\n[2] fetch_search")
from src.crawler.fetch_search import fetch_search

check("search '台灣' 至少 1 筆結果", lambda: fetch_search(client, "台灣", max_results=3))

# ── 3. channel uploads ─────────────────────────────────────────────────────
print("\n[3] fetch_channel_uploads")
from src.crawler.fetch_channel_uploads import fetch_channel_uploads

check(f"channel {test_channel_id[:24]} 至少 1 支影片",
      lambda: fetch_channel_uploads(client, test_channel_id, max_results=3))

# ── 4. detect_shorts ───────────────────────────────────────────────────────
print("\n[4] detect_shorts")
from src.crawler.detect_shorts import detect_shorts

result_long, code_long = detect_shorts(client, _FALLBACK_VIDEO_ID)
check(f"長影片 {_FALLBACK_VIDEO_ID} → 'long' (got '{result_long}' {code_long})",
      lambda: result_long == "long")

result_t, code_t = detect_shorts(client, test_video_id)
check(f"trending/fallback {test_video_id} → 結果非 None (got '{result_t}' {code_t})",
      lambda: result_t is not None)

# ── 5. fetch_static ────────────────────────────────────────────────────────
print("\n[5] fetch_static")
from src.crawler.fetch_static import fetch_static

static = check(f"fetch_static {test_video_id}",
               lambda: fetch_static(client, test_video_id, DATA_DIR))
if static:
    for field in ("title", "channel_id", "publish_time", "duration_seconds",
                  "is_shorts", "video_status", "subscriber_count_at_fetch", "comment_count_at_fetch"):
        val = static.get(field)
        tag = _PASS if val is not None else "~"
        print(f"       {tag} {field} = {val!r}")

# ── 6. fetch_timeseries ────────────────────────────────────────────────────
print("\n[6] fetch_timeseries")
from src.crawler.fetch_timeseries import fetch_timeseries_snapshot

pub = static.get("publish_time") if static else None
ts = check(f"fetch_timeseries {test_video_id}",
           lambda: fetch_timeseries_snapshot(client, test_video_id, pub, DATA_DIR))
if ts:
    for field in ("view_count", "like_count", "comment_count", "subscriber_count", "video_status"):
        val = ts.get(field)
        tag = _PASS if val is not None else "~"
        print(f"       {tag} {field} = {val!r}")

# ── 7. fetch_comments ──────────────────────────────────────────────────────
print("\n[7] fetch_comments")
from src.crawler.fetch_comments import fetch_comments_snapshot

n = check(f"fetch_comments {test_video_id} [t1h] 至少 1 則",
          lambda: fetch_comments_snapshot(client, test_video_id, "t1h", DATA_DIR, max_comments=10))
if n:
    print(f"       ↳ 抓到 {n} 則留言")

# ── summary ────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok in results if ok)
total  = len(results)
print(f"\n{'─'*40}")
print(f"結果：{passed}/{total} 通過")
if passed < total:
    print("失敗項目：")
    for name, ok in results:
        if not ok:
            print(f"  ✗ {name}")

# ── cleanup ────────────────────────────────────────────────────────────────
print("\n清理測試產生的檔案…")

# 先關掉所有 file handler，否則 Windows 不讓刪 log 檔
for handler in logging.root.handlers[:]:
    if isinstance(handler, logging.FileHandler):
        handler.close()
        logging.root.removeHandler(handler)

for path in [DATA_DIR / "raw", DATA_DIR / "state.db", _log_dir]:
    try:
        if path.exists():
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    except Exception as e:
        print(f"  無法刪除 {path}: {e}")

print("完成。")
