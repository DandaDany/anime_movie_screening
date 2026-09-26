from __future__ import annotations

import json
import re
import unittest
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

KEYWORDS = [
    "SessionId", "SessionID", "sessionId", "VistaDataV2", "GetSession",
    "Seat", "seat", "Booking", "booking", "Order", "order",
    "Ticket", "ticket", "Login", "login",
]


def snippet(text: str, keyword: str, radius: int = 2200):
    idx = text.find(keyword)
    return None if idx < 0 else text[max(0, idx-radius):idx+radius]


def fetch_site(request, label: str, url: str):
    result = {"url": url}
    try:
        response = request.get(url, timeout=10000)
        result["status"] = response.status
        html = response.text()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(label + "_PROBE " + json.dumps(result, ensure_ascii=False))
        return

    result["html_hits"] = {kw: snippet(html, kw) for kw in KEYWORDS if kw in html}
    soup = BeautifulSoup(html, "html.parser")
    scripts = [urljoin(url, node.get("src")) for node in soup.select("script[src]") if node.get("src")]
    result["scripts"] = scripts
    result["script_hits"] = []
    for src in scripts[:20]:
        if not any(host in src for host in ("skcinemas.com", "bonjays.com")):
            continue
        try:
            script_response = request.get(src, timeout=7000)
            text = script_response.text()
        except Exception as exc:
            result["script_hits"].append({"src": src, "error": f"{type(exc).__name__}: {exc}"})
            continue
        hits = {kw: snippet(text, kw) for kw in KEYWORDS if kw in text}
        if hits:
            result["script_hits"].append({"src": src, "hits": hits})
    print(label + "_PROBE " + json.dumps(result, ensure_ascii=False))


class CinemaBookingResearchProbe(unittest.TestCase):
    def test_shinkong_frontend_routes(self):
        with sync_playwright() as p:
            request = p.request.new_context(
                extra_http_headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9",
                }
            )
            try:
                fetch_site(request, "SK_PRODUCTION", "https://www.skcinemas.com/films?c=1001")
                fetch_site(request, "SK_MIRROR_HOME", "https://skcwww.bonjays.com/")
                fetch_site(request, "SK_MIRROR_SESSIONS", "https://skcwww.bonjays.com/Sessions/Sessions")
                fetch_site(request, "SK_MIRROR_FILMS", "https://skcwww.bonjays.com/Films/Films?filmType=NowShowing")
            finally:
                request.dispose()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
