"""Fetch stage. Order of preference:
1. A file a person placed in data/inbox/<source_key>.(html|pdf|txt)  -> method 'manual_upload'
2. HTTP GET with requests                                             -> method 'http'
3. Playwright (only when use_playwright=True and HTTP gave no usable body) -> method 'playwright'
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

import requests

from ..db import ROOT

INBOX = ROOT / "data" / "inbox"
UA = "GCCAtlasResearchBot/0.1 (public-source research)"
TIMEOUT = 25


@dataclass
class FetchResult:
    ok: bool
    method: str
    content: bytes = b""
    content_type: str = ""
    http_status: int | None = None
    status: str = "failed"  # retrieved | http_error | network_blocked | failed
    error: str = ""

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest() if self.content else None


def _inbox_file(source_key, inbox):
    for ext, ctype in (("pdf", "application/pdf"), ("html", "text/html"), ("txt", "text/plain")):
        p = Path(inbox) / f"{source_key}.{ext}"
        if p.exists():
            return p, ctype
    return None, None


def _classify(exc):
    msg = str(exc)
    if "Tunnel connection failed" in msg or "CONNECT tunnel failed" in msg or "ProxyError" in type(exc).__name__:
        return "network_blocked"
    return "failed"


def fetch_http(url, session=None):
    s = session or requests.Session()
    try:
        r = s.get(url, timeout=TIMEOUT, headers={"User-Agent": UA}, allow_redirects=True)
    except requests.RequestException as exc:
        return FetchResult(False, "http", status=_classify(exc), error=f"{type(exc).__name__}: {str(exc)[:300]}")
    ctype = r.headers.get("content-type", "").split(";")[0].strip()
    if 200 <= r.status_code < 300 and r.content:
        return FetchResult(True, "http", r.content, ctype, r.status_code, "retrieved")
    return FetchResult(False, "http", http_status=r.status_code, status="http_error", error=f"HTTP {r.status_code}")


def fetch_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return FetchResult(False, "playwright", status="failed", error=str(exc))
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=UA)
            resp = page.goto(url, timeout=TIMEOUT * 1000, wait_until="networkidle")
            html = page.content().encode()
            status = resp.status if resp else None
            browser.close()
    except Exception as exc:  # playwright raises its own error types
        return FetchResult(False, "playwright", status=_classify(exc), error=f"{type(exc).__name__}: {str(exc)[:300]}")
    if status and 200 <= status < 300 and html:
        return FetchResult(True, "playwright", html, "text/html", status, "retrieved")
    return FetchResult(False, "playwright", http_status=status, status="http_error", error=f"HTTP {status}")


def fetch(source_key, url, inbox=INBOX, use_playwright=False, session=None):
    path, ctype = _inbox_file(source_key, inbox)
    if path:
        return FetchResult(True, "manual_upload", path.read_bytes(), ctype, None, "retrieved")
    res = fetch_http(url, session)
    if not res.ok and use_playwright and res.status != "network_blocked":
        res = fetch_playwright(url)
    return res
