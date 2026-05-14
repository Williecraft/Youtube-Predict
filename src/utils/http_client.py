"""
Shared HTTP client for all crawlers.

Priority:
  1. InnerTube / page-embedded JSON  (post_innertube / get_watch_page)
  2. Plain HTML scraping             (get)
  3. Selenium                        (not implemented here; fallback in individual fetchers)
"""

from __future__ import annotations

import json
import random
import time
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

_INNERTUBE_BASE = "https://www.youtube.com/youtubei/v1"
_INNERTUBE_CLIENT: dict = {
    "clientName": "WEB",
    "clientVersion": "2.20240510.01.00",
    "hl": "zh-TW",
    "gl": "TW",
}

# retry delays in seconds for each attempt after the first
_RETRY_DELAYS = [3, 8, 20]

# module-level stop flag; run_scheduler sets this to True to interrupt sleeps
_stop = False


def set_stop(val: bool = True):
    global _stop
    _stop = val


def _sleep(seconds: float):
    """Sleep in 0.5s chunks so Ctrl+C / _stop can interrupt."""
    end = time.monotonic() + seconds
    while not _stop:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.5, remaining))


class YouTubeClient:
    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
        })
        # Bypass YouTube consent / GDPR gate
        self._session.cookies.set("SOCS", "CAI", domain=".youtube.com")
        self._rotate_ua()

    def _rotate_ua(self):
        self._session.headers["User-Agent"] = random.choice(_USER_AGENTS)

    # ── generic GET ────────────────────────────────────────────────────────

    def get(self, url: str, params: dict | None = None, timeout: int = 20) -> requests.Response | None:
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if _stop:
                return None
            if delay:
                _sleep(delay + random.uniform(0, 2))
            try:
                resp = self._session.get(url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    wait = 90 + random.uniform(0, 30)
                    logger.warning("429 on GET %s — backing off %.0fs", url, wait)
                    _sleep(wait)
                    continue
                if resp.status_code >= 500:
                    logger.warning("HTTP %d GET %s (attempt %d/%d)", resp.status_code, url, attempt + 1, len(_RETRY_DELAYS) + 1)
                    continue
                return resp
            except requests.RequestException as exc:
                logger.warning("GET %s failed (attempt %d): %s", url, attempt + 1, exc)
        logger.error("GET %s exhausted retries", url)
        return None

    def get_no_redirect(self, url: str, timeout: int = 10) -> int | None:
        """GET without following redirects; returns HTTP status code or None on error."""
        try:
            resp = self._session.get(url, allow_redirects=False, timeout=timeout)
            return resp.status_code
        except requests.RequestException as exc:
            logger.warning("get_no_redirect %s: %s", url, exc)
            return None

    # ── InnerTube POST ─────────────────────────────────────────────────────

    def post_innertube(
        self,
        endpoint: str,
        payload: dict,
        client_extra: dict | None = None,
        timeout: int = 20,
    ) -> dict | None:
        """
        client_extra: merged into the client context (e.g. {"gl": "JP"} for region).
        """
        url = f"{_INNERTUBE_BASE}/{endpoint}"
        client = {**_INNERTUBE_CLIENT, **(client_extra or {})}
        body = {"context": {"client": client}, **payload}
        headers = {
            "Content-Type": "application/json",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": client["clientVersion"],
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        }
        req_params = {"prettyPrint": "false"}
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if _stop:
                return None
            if delay:
                _sleep(delay + random.uniform(0, 2))
            try:
                resp = self._session.post(url, json=body, headers=headers, params=req_params, timeout=timeout)
                if resp.status_code == 429:
                    wait = 90 + random.uniform(0, 30)
                    logger.warning("429 innertube/%s — backing off %.0fs", endpoint, wait)
                    _sleep(wait)
                    continue
                if resp.status_code >= 400:
                    logger.warning("HTTP %d innertube/%s (attempt %d)", resp.status_code, endpoint, attempt + 1)
                    continue
                return resp.json()
            except (requests.RequestException, json.JSONDecodeError) as exc:
                logger.warning("innertube/%s error (attempt %d): %s", endpoint, attempt + 1, exc)
        logger.error("innertube/%s exhausted retries", endpoint)
        return None

    # ── watch-page helpers ─────────────────────────────────────────────────

    def get_watch_page(self, video_id: str) -> tuple[dict, dict]:
        """Return (ytInitialData, ytInitialPlayerResponse) from watch page."""
        resp = self.get(f"https://www.youtube.com/watch?v={video_id}", params={"hl": "zh-TW"})
        if resp is None or resp.status_code != 200:
            return {}, {}
        html = resp.text
        return extract_js_var(html, "ytInitialData"), extract_js_var(html, "ytInitialPlayerResponse")

    def jitter_sleep(self, min_s: float = 1.0, max_s: float = 3.0):
        _sleep(random.uniform(min_s, max_s))


# ── HTML JSON extraction ────────────────────────────────────────────────────

def extract_js_var(html: str, var_name: str) -> dict:
    """
    Extract a JSON object assigned to a JS variable in the page HTML.
    Handles both:
      var ytInitialData = {...};
      window["ytInitialData"] = {...};
    """
    for marker in (f"{var_name} = ", f'"{var_name}":'):
        idx = html.find(marker)
        if idx != -1:
            brace_idx = html.find("{", idx + len(marker))
            if brace_idx != -1:
                try:
                    data, _ = json.JSONDecoder().raw_decode(html, brace_idx)
                    if isinstance(data, dict):
                        return data
                except (json.JSONDecodeError, ValueError):
                    pass
    return {}


# ── Numeric string parser (e.g. "1.2K" → 1200) ────────────────────────────

def parse_count_text(text: str | None) -> int | None:
    if not text:
        return None
    text = text.replace(",", "").strip()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000,
                   "千": 1_000, "萬": 10_000, "億": 100_000_000}
    for suffix, mult in multipliers.items():
        if text.upper().endswith(suffix.upper()):
            try:
                return int(float(text[:-1]) * mult)
            except ValueError:
                pass
    try:
        return int(float(text))
    except ValueError:
        return None


# ── Deep dict navigation ───────────────────────────────────────────────────

def dig(data: Any, *keys) -> Any:
    """Safely navigate nested dicts/lists. Returns None on any miss."""
    for key in keys:
        if data is None:
            return None
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and isinstance(key, int):
            data = data[key] if key < len(data) else None
        else:
            return None
    return data
