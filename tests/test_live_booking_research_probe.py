from __future__ import annotations

import json
import re
import unittest
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

KEYWORDS = [
    "SessionId", "SessionID", "sessionId", "sessionID",
    "CinemaList", "VistaDataV2", "GetSession",
    "Seat", "seat", "Booking", "booking", "Order", "order",
    "Ticket", "ticket", "Login", "login",
]


def snippets(text: str, keyword: str, radius: int = 1800, limit: int = 4):
    out = []
    start = 0
    while len(out) < limit:
        idx = text.find(keyword, start)
        if idx < 0:
            break
        out.append(text[max(0, idx - radius): idx + radius])
        start = idx + len(keyword)
    return out


def inspect_page(page, label: str, url: str, timeout: int = 30000):
    requests = []
    responses = []
    page.on("request", lambda req: requests.append(req.url))
    page.on("response", lambda res: responses.append({"url": res.url, "status": res.status}))
    nav_error = None
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as exc:
        nav_error = f"{type(exc).__name__}: {exc}"
    page.wait_for_timeout(8000)

    html = page.content()
    scripts = page.eval_on_selector_all(
        "script[src]", "els => els.map(e => new URL(e.src, location.href).href)"
    )
    inline = page.eval_on_selector_all(
        "script:not([src])", "els => els.map(e => e.textContent || '')"
    )

    script_hits = []
    for src in scripts:
        try:
            response = page.request.get(src, timeout=20000)
            text = response.text()
        except Exception as exc:
            script_hits.append({"src": src, "error": f"{type(exc).__name__}: {exc}"})
            continue
        hits = {}
        for kw in KEYWORDS:
            ss = snippets(text, kw, radius=1200, limit=2)
            if ss:
                hits[kw] = ss
        if hits:
            script_hits.append({"src": src, "hits": hits})

    inline_hits = []
    for idx, text in enumerate(inline):
        hits = {}
        for kw in KEYWORDS:
            ss = snippets(text, kw, radius=1600, limit=2)
            if ss:
                hits[kw] = ss
        if hits:
            inline_hits.append({"index": idx, "hits": hits})

    controls = []
    loc = page.locator("a, button, [onclick], [data-session], [data-sessionid], [data-id]")
    count = min(loc.count(), 800)
    for i in range(count):
        node = loc.nth(i)
        try:
            text = node.inner_text(timeout=300).strip()
            href = node.get_attribute("href") or ""
            onclick = node.get_attribute("onclick") or ""
            outer = node.evaluate("el => el.outerHTML")
        except Exception:
            continue
        joined = " ".join([text, href, onclick, outer])
        if (
            re.search(r"\b\d{1,2}:\d{2}\b", text)
            or re.search(r"session|booking|ticket|seat|order|訂票|座位", joined, re.I)
        ):
            controls.append({
                "text": text[:180],
                "href": href[:700],
                "onclick": onclick[:700],
                "outer": outer[:1800],
            })
        if len(controls) >= 80:
            break

    html_hits = {}
    for kw in KEYWORDS:
        ss = snippets(html, kw, radius=1500, limit=3)
        if ss:
            html_hits[kw] = ss

    interesting_requests = [
        x for x in requests
        if re.search(r"api|session|seat|booking|ticket|order|vista|login", x, re.I)
    ][-120:]
    interesting_responses = [
        x for x in responses
        if re.search(r"api|session|seat|booking|ticket|order|vista|login", x["url"], re.I)
    ][-120:]

    result = {
        "label": label,
        "requested_url": url,
        "final_url": page.url,
        "title": page.title(),
        "nav_error": nav_error,
        "scripts": scripts,
        "script_hits": script_hits,
        "inline_hits": inline_hits,
        "html_hits": html_hits,
        "controls": controls,
        "requests": interesting_requests,
        "responses": interesting_responses,
    }
    print(label + "_PROBE " + json.dumps(result, ensure_ascii=False))
    return result


class CinemaBookingResearchProbe(unittest.TestCase):
    def test_miranew_and_shinkong_booking_surfaces(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for label, url in [
                    ("MIRANEW", "https://www.miranewcinemas.com/Booking/Timetable"),
                    ("MIRANEW_HOME", "https://www.miranewcinemas.com/"),
                    ("SKCINEMAS", "https://www.skcinemas.com/films?c=1001"),
                    ("SKCINEMAS_HOME", "https://www.skcinemas.com/"),
                ]:
                    context = browser.new_context(
                        locale="zh-TW",
                        timezone_id="Asia/Taipei",
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                        viewport={"width": 1366, "height": 900},
                    )
                    page = context.new_page()
                    try:
                        inspect_page(page, label, url, timeout=20000)
                    finally:
                        context.close()
            finally:
                browser.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
