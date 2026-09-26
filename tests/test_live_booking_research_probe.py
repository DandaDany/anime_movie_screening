from __future__ import annotations

import json
import re
import unittest

from playwright.sync_api import sync_playwright

KEYWORDS = [
    "SessionId", "SessionID", "sessionId", "CinemaList", "VistaDataV2",
    "GetSession", "Seat", "seat", "Booking", "booking", "Order", "order",
    "Ticket", "ticket", "Login", "login",
]


def one_snippet(text: str, keyword: str, radius: int = 2200):
    idx = text.find(keyword)
    if idx < 0:
        return None
    return text[max(0, idx - radius):idx + radius]


def inspect(page, label: str, url: str, *, wait_until="domcontentloaded"):
    reqs = []
    page.on("request", lambda req: reqs.append(req.url))
    err = None
    try:
        page.goto(url, wait_until=wait_until, timeout=12000)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    page.wait_for_timeout(3500)

    html = page.content()
    scripts = page.eval_on_selector_all(
        "script[src]", "els => els.map(e => new URL(e.src, location.href).href)"
    )
    inline = page.eval_on_selector_all(
        "script:not([src])", "els => els.map(e => e.textContent || '')"
    )

    inline_hits = []
    for i, text in enumerate(inline):
        hits = {kw: one_snippet(text, kw) for kw in KEYWORDS if kw in text}
        if hits:
            inline_hits.append({"index": i, "hits": hits})

    script_hits = []
    for src in scripts[:20]:
        try:
            res = page.request.get(src, timeout=8000)
            text = res.text()
        except Exception as exc:
            script_hits.append({"src": src, "error": f"{type(exc).__name__}: {exc}"})
            continue
        hits = {kw: one_snippet(text, kw) for kw in KEYWORDS if kw in text}
        if hits:
            script_hits.append({"src": src, "hits": hits})

    controls = []
    loc = page.locator("a,button,[onclick],[data-id],[data-session],[data-sessionid]")
    for i in range(min(loc.count(), 500)):
        node = loc.nth(i)
        try:
            text = node.inner_text(timeout=250).strip()
            href = node.get_attribute("href") or ""
            onclick = node.get_attribute("onclick") or ""
            outer = node.evaluate("el => el.outerHTML")
        except Exception:
            continue
        joined = " ".join((text, href, onclick, outer))
        if re.search(r"\b\d{1,2}:\d{2}\b|session|booking|ticket|seat|order|訂票|座位", joined, re.I):
            controls.append({"text": text[:120], "href": href[:500], "onclick": onclick[:500], "outer": outer[:1200]})
        if len(controls) >= 50:
            break

    html_hits = {kw: one_snippet(html, kw) for kw in KEYWORDS if kw in html}
    interesting_reqs = [
        x for x in reqs if re.search(r"api|session|seat|booking|ticket|order|vista|login", x, re.I)
    ][-80:]

    result = {
        "final_url": page.url,
        "title": page.title(),
        "error": err,
        "scripts": scripts,
        "inline_hits": inline_hits,
        "script_hits": script_hits,
        "html_hits": html_hits,
        "controls": controls,
        "requests": interesting_reqs,
    }
    print(label + "_PROBE " + json.dumps(result, ensure_ascii=False))
    return result


class CinemaBookingResearchProbe(unittest.TestCase):
    def test_booking_flows(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei")
                try:
                    inspect(context.new_page(), "MIRANEW", "https://www.miranewcinemas.com/Booking/Timetable")
                finally:
                    context.close()

                context = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei")
                try:
                    inspect(context.new_page(), "SKCINEMAS", "https://www.skcinemas.com/films?c=1001", wait_until="commit")
                finally:
                    context.close()

                # The current production host is intermittently unreachable from
                # GitHub Actions. This public mirror exposes the same new-site
                # membership/ticketing frontend and is useful for route discovery.
                context = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei")
                try:
                    inspect(context.new_page(), "SK_MIRROR", "https://skcwww.bonjays.com/", wait_until="domcontentloaded")
                finally:
                    context.close()
            finally:
                browser.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
