from __future__ import annotations

import json
import unittest
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


TARGETS = [
    "https://skcwww.bonjays.com/Sessions/Sessions",
    "https://skcwww.bonjays.com/Sessions/Sessions?c=1001",
    "https://skcwww.bonjays.com/Sessions/Sessions?cinema=1001",
    "https://skcwww.bonjays.com/Sessions/Sessions?CinemasID=1001",
]


class ShinKongExactBookingProbe(unittest.TestCase):
    def test_extract_session_booking_contract(self):
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

                    forms = []
                    for form in soup.select("form"):
                        forms.append({
                            "action": form.get("action"),
                            "method": form.get("method"),
                            "inputs": [
                                {
                                    "name": node.get("name"),
                                    "value": node.get("value"),
                                    "type": node.get("type"),
                                }
                                for node in form.select("input[name]")
                            ][:50],
                            "selects": [
                                {
                                    "name": sel.get("name"),
                                    "id": sel.get("id"),
                                    "options": [
                                        {"value": opt.get("value"), "text": opt.get_text(" ", strip=True)}
                                        for opt in sel.select("option")
                                    ][:30],
                                }
                                for sel in form.select("select")
                            ][:20],
                        })

                    data_nodes = []
                    for node in soup.select("[data-action-url], [data-booking-url], [data-session], [data-sessionid], [data-id], [auth]"):
                        data_nodes.append({
                            "tag": node.name,
                            "text": node.get_text(" ", strip=True)[:160],
                            "attrs": {
                                k: v
                                for k, v in node.attrs.items()
                                if k.startswith("data-") or k in {"auth", "href", "id", "class"}
                            },
                        })
                        if len(data_nodes) >= 120:
                            break

                    session_bundle = ""
                    session_bundle_url = ""
                    for node in soup.select("script[src]"):
                        src = urljoin(url, node.get("src"))
                        if "/bundles/sessions" in src:
                            session_bundle_url = src
                            session_bundle = request.get(src, timeout=10000).text()
                            break

                    print("SK_EXACT_BOOKING_PROBE " + json.dumps({
                        "url": url,
                        "status": response.status,
                        "final_url": response.url,
                        "forms": forms,
                        "data_nodes": data_nodes,
                        "session_bundle_url": session_bundle_url,
                        "session_bundle": session_bundle[:60000],
                    }, ensure_ascii=False))
            finally:
                request.dispose()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
