"""
Watchdog: 自動重啟 crawl.py，掛掉就重開。

用法：
    python scripts/watchdog.py

按 Ctrl+C 停止。
"""

import subprocess
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
CRAWL = str(REPO_ROOT / "crawl.py")
LOG_PATH = REPO_ROOT / "logs" / "watchdog.log"

LOG_PATH.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("watchdog")

MIN_UPTIME_S = 30    # 若啟動後 <30s 就死，視為快速失敗，等久一點再重啟
RESTART_DELAY_S = 5  # 正常重啟等待秒數
FAST_FAIL_DELAY_S = 60


def run():
    attempt = 0
    while True:
        attempt += 1
        start = time.time()
        logger.info("=== Starting crawl.py (attempt %d) ===", attempt)

        try:
            proc = subprocess.Popen(
                [PYTHON, CRAWL],
                cwd=str(REPO_ROOT),
            )
            proc.wait()
            elapsed = time.time() - start
            code = proc.returncode
            logger.info("crawl.py exited (code=%s, uptime=%.0fs)", code, elapsed)
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user.")
            try:
                proc.terminate()
            except Exception:
                pass
            break
        except Exception as e:
            elapsed = time.time() - start
            logger.error("Failed to start crawl.py: %s", e)

        delay = FAST_FAIL_DELAY_S if elapsed < MIN_UPTIME_S else RESTART_DELAY_S
        logger.info("Restarting in %ds ...", delay)
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user.")
            break


if __name__ == "__main__":
    run()
