from __future__ import annotations

import json
import re
import unittest
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class CinemaBookingResearchProbe(unittest.TestCase):
    def test_shinkong_session_route(self):
        with sync_playwright() as p:
            request = p.request.new_context(
                extra_http_headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh;q=0.9"}
            )
            try:
                base = "https://skcwww.bonjays.com/Sessions/Sessions"
                res = request.get(base, timeout=10000)
                html = res.text()
                soup = BeautifulSoup(html, "html.parser")
                scripts = [urljoin(base, n.get("src")) for n in soup.select("script[src]") if n.get("src")]
                actions = sorted(set(re.findall(r'data-action-url=["\\\']([^"\\\']+)', html, re.I)))
                time_nodes = []
                for node in soup.find_all(string=re.compile(r'^\\s*\\d{1,2}:\\d{2}\\s*$')):
                    parent = node.parent
                    for _ in range(4):
                        if parent and parent.parent:
                            parent = parent.parent
                    if parent:
                        time_nodes.append(str(parent)[:3000])
                    if len(time_nodes) >= 12:
                        break
                session_src = next((x for x in scripts if "/bundles/sessions" in x), "")
                js = request.get(session_src, timeout=10000).text() if session_src else ""
                route_paths = []
                snippets = {}
                for kw in ["ajax", "url:", "data-action-url", "window.location", "location.href", "Sessions/", "Ticket", "Order"]:
                    i = js.find(kw)
                    if i >= 0:
                        snippets[kw] = js[max(0, i-2500):i+5000]
                print("SK_SESSION_ROUTE_PROBE " + json.dumps({
                    "status": res.status,
                    "scripts": scripts,
                    "data_action_urls": actions,
                    "time_nodes": time_nodes,
                    "session_bundle": session_src,
                    "route_paths": route_paths,
                    "snippets": snippets,
                }, ensure_ascii=False))
            finally:
                request.dispose()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
