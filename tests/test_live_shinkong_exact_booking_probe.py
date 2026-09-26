from __future__ import annotations

import json
import unittest
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

TARGETS = [
    "https://skcwww.bonjays.com/films?c=1001",
    "https://skcwww.bonjays.com/Films/Films?filmType=NowShowing",
    "https://skcwww.bonjays.com/Sessions/Sessions?cinemaId=1001",
]

KEYWORDS = [
    "VistaDataV2", "SessionID", "SessionId", "bookingUrl", "data-booking-url",
    "GetSession", "booking", "Booking", "Seat", "seat",
]


def around(text: str, needle: str, radius: int = 2600):
    idx = text.find(needle)
    return None if idx < 0 else text[max(0, idx-radius):idx+radius]


class ShinKongExactBookingProbe(unittest.TestCase):
    def test_extract_booking_generation_logic(self):
        with sync_playwright() as p:
            request = p.request.new_context(
                extra_http_headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9",
                }
            )
            try:
                for url in TARGETS:
                    response = request.get(url, timeout=10000)
                    html = response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    scripts = [urljoin(url, n.get("src")) for n in soup.select("script[src]") if n.get("src")]
                    own_scripts = [s for s in scripts if "bonjays.com/" in s]

                    script_hits = []
                    for src in own_scripts[:20]:
                        try:
                            js = request.get(src, timeout=8000).text()
                        except Exception as exc:
                            script_hits.append({"src": src, "error": f"{type(exc).__name__}: {exc}"})
                            continue
                        hits = {kw: around(js, kw) for kw in KEYWORDS if kw in js}
                        if hits:
                            script_hits.append({"src": src, "hits": hits})

                    data_nodes = []
                    for node in soup.select("[data-booking-url], [data-action-url], [data-session], [data-sessionid], [data-id]"):
                        attrs = {k: v for k, v in node.attrs.items() if k.startswith("data-") or k in {"href", "auth"}}
                        text = node.get_text(" ", strip=True)[:160]
                        if "data-booking-url" in attrs or "session" in str(attrs).lower() or "booking" in str(attrs).lower() or text:
                            data_nodes.append({"tag": node.name, "text": text, "attrs": attrs})
                        if len(data_nodes) >= 100:
                            break

                    html_hits = {kw: around(html, kw) for kw in KEYWORDS if kw in html}
                    print("SK_BOOKING_LOGIC_PROBE " + json.dumps({
                        "url": url,
                        "status": response.status,
                        "final_url": response.url,
                        "scripts": scripts,
                        "script_hits": script_hits,
                        "html_hits": html_hits,
                        "data_nodes": data_nodes,
                    }, ensure_ascii=False))
            finally:
                request.dispose()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
