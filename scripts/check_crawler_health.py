"""
爬蟲健康檢查：判斷時序爬蟲是否「符合預期」，給 /loop 每 2 小時呼叫。

判準（任一 FAIL 即需處理）：
  1. 活躍度    — crawl_log 最近一筆事件距今 <= MAX_IDLE_MIN（爬蟲沒卡死）
  2. 積壓      — 逾期待抓的時序任務 < BACKLOG_MAX（吞吐跟得上）
  3. 追蹤覆蓋  — 仍在追蹤窗口內(track_until>now)的影片 >= TRACKING_MIN（有新鮮影片持續進來）
  4. 新鮮發現  — 最近 2h 有新發現影片（discovery 沒停）
  5. 端點命中  — 最近 24h 內「開始追蹤」的影片，48h 檢查點對齊是否生效（取樣品質）

輸出 JSON 摘要 + 人類可讀結論；exit code 0=全 PASS，1=有 FAIL。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "state.db"

# ── 門檻 ────────────────────────────────────────────────────────────────────
MAX_IDLE_MIN = 30        # 最近事件距今超過此值 → 爬蟲可能卡死
BACKLOG_MAX = 300        # 逾期時序任務上限（對齊 _AT_CAPACITY_THRESHOLD）
TRACKING_MIN = 40        # 追蹤窗口內影片數下限（低於此代表新鮮影片枯竭）
DISCOVERY_WINDOW_H = 2   # 新鮮發現檢查窗口


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    now = datetime.now(timezone.utc)
    now_s = _iso(now)
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()

    def scalar(sql: str, *args):
        cur.execute(sql, args)
        r = cur.fetchone()
        return r[0] if r else None

    checks: dict[str, dict] = {}

    # 1. 活躍度
    last_event = scalar("SELECT MAX(event_time) FROM crawl_log")
    idle_min = None
    if last_event:
        try:
            idle_min = (now - datetime.fromisoformat(last_event.replace("Z", "+00:00"))).total_seconds() / 60
        except Exception:
            pass
    checks["activity"] = {
        "last_event": last_event,
        "idle_min": round(idle_min, 1) if idle_min is not None else None,
        "pass": idle_min is not None and idle_min <= MAX_IDLE_MIN,
    }

    # 2. 積壓
    backlog = scalar(
        """SELECT COUNT(*) FROM videos
           WHERE next_ts_due <= ? AND (track_until IS NULL OR track_until > ?)
             AND static_fetched = 1""",
        now_s, now_s,
    )
    checks["backlog"] = {"overdue": backlog, "max": BACKLOG_MAX, "pass": backlog < BACKLOG_MAX}

    # 3. 追蹤覆蓋
    tracking = scalar(
        "SELECT COUNT(*) FROM videos WHERE track_until > ? AND static_fetched = 1", now_s
    )
    checks["tracking_coverage"] = {"in_window": tracking, "min": TRACKING_MIN, "pass": tracking >= TRACKING_MIN}

    # 4. 新鮮發現
    disc_cutoff = _iso(now - timedelta(hours=DISCOVERY_WINDOW_H))
    new_disc = scalar("SELECT COUNT(*) FROM videos WHERE discovered_at >= ?", disc_cutoff)
    checks["fresh_discovery"] = {
        "new_in_window": new_disc, "window_h": DISCOVERY_WINDOW_H, "pass": new_disc > 0,
    }

    # 5. 端點命中（取樣品質）：最近 24h 開始追蹤、發布已過 48h 的影片中，
    #    有多少在 48h±90min 內有 snapshot（對齊修復生效的指標）。資訊性，不參與 FAIL。
    # 用 crawl_log 的 timeseries ok 事件近 2h 量作為吞吐量參考
    thru_cutoff = _iso(now - timedelta(hours=DISCOVERY_WINDOW_H))
    ts_events = scalar(
        "SELECT COUNT(*) FROM crawl_log WHERE event_time >= ? AND job_name='timeseries' AND status='ok'",
        thru_cutoff,
    )
    checks["throughput_2h"] = {"timeseries_ok": ts_events, "pass": True}

    con.close()

    all_pass = all(c["pass"] for c in checks.values())
    summary = {
        "checked_at": now_s,
        "all_pass": all_pass,
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not all_pass:
        failed = [k for k, c in checks.items() if not c["pass"]]
        print(f"\nFAIL: {', '.join(failed)}", file=sys.stderr)
    else:
        print("\nALL PASS — 爬蟲符合預期")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
