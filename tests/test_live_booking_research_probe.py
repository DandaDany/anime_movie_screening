from __future__ import annotations

import json
import unittest
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def around_all(text: str, needle: str, radius: int = 3500, limit: int = 6):
    lower = text.lower()
    target = needle.lower()
    out = []
    start = 0
    while len(out) < limit:
        idx = lower.find(target, start)
        if idx < 0:
            break
        out.append(text[max(0, idx-radius):idx+radius])
        start = idx + len(target)
    return out


class CinemaBookingResearchProbe(unittest.TestCase):
    def test_shinkong_event_mechanics(self):
        with sync_playwright() as p:
            request = p.request.new_context(extra_http_headers={"User-Agent": "Mozilla/5.0"})
            try:
                page_url = "https://skcwww.bonjays.com/Sessions/Sessions"
                html = request.get(page_url, timeout=10000).text()
                soup = BeautifulSoup(html, "html.parser")
                scripts = [urljoin(page_url, n.get("src")) for n in soup.select("script[src]") if n.get("src")]
                selected = [x for x in scripts if "/bundles/jquery" in x or "/bundles/sessions" in x]
                results = []
                for src in selected:
                    js = request.get(src, timeout=10000).text()
                    hits = {}
                    for needle in [
                        "skcEvent", "staticContent", "session", "film", "order",
                        "buy", "ticket", "data-action-url", "window.location",
                        "location.href", "ajax", "apiUrl",
                    ]:
                        parts = around_all(js, needle)
                        if parts:
                            hits[needle] = parts
                    results.append({"src": src, "length": len(js), "hits": hits, "head": js[:12000]})
                print("SK_EVENT_MECHANICS_PROBE " + json.dumps(results, ensure_ascii=False))
            finally:
                request.dispose()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
