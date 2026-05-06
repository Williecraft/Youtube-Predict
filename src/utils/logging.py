"""
兩層 logging：

  summary   → 終端機（只顯示開始/找到幾部/錯誤）+ 寫進 log 檔
  get_logger → 只寫進 log 檔（HTTP 細節、個別影片 fetch、debug 資訊）

使用方式：
  from src.utils.logging import get_logger, summary

  summary.info("Scheduler starting")          # 終端機 + 檔案
  logger = get_logger(__name__)
  logger.debug("fetching %s", video_id)       # 只進檔案
"""

import logging
import sys
from pathlib import Path

# ── formats ───────────────────────────────────────────────────────────────
_FILE_FMT    = logging.Formatter("%(asctime)s %(levelname)-8s %(name)-30s %(message)s",
                                  datefmt="%Y-%m-%dT%H:%M:%S")
_CONSOLE_FMT = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

# ── root logger (file only) ────────────────────────────────────────────────
_root = logging.getLogger()
_root.setLevel(logging.DEBUG)

# ── summary logger (console + file via propagation) ────────────────────────
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_CONSOLE_FMT)

summary = logging.getLogger("summary")
summary.addHandler(_console_handler)
summary.propagate = True   # also flows to root → file


def setup_file_logging(log_dir: Path | str, filename: str = "crawler.log") -> None:
    """
    Call once at startup to attach the file handler to the root logger.
    All loggers (including summary) will then write to this file.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_dir / filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FILE_FMT)
    _root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to file only (no console output)."""
    return logging.getLogger(name)
