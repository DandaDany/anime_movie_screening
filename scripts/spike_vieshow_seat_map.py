#!/usr/bin/env python3
"""Test whether VIESHOW redirector can be used as a public seat-preview handoff.

Read-only only. No login, ticket selection, seat click, reservation, checkout, or payment.
"""

from __future__ import annotations

import json
import urllib.parse
from playwright.sync_api import sync_playwright

SEAT_URL = (
    "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
REDIRECTOR = (
    "https://www.vscinemas.com.tw/redirector.aspx"
    "?id=17&x=1&y=" + urllib.parse.quote(SEAT_URL, safe="")
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        trace = []

        def on_request(req):
            if "SessionSeats.aspx" in req.url or "redirector.aspx" in req.url:
                headers = req.all_headers()
                trace.append({
                    "url": req.url,
                    "method": req.method,
                    "referer": headers.get("referer"),
                    "sec_fetch_site": headers.get("sec-fetch-site"),
                })

        context.on("request", on_request)

        resp = page.goto(REDIRECTOR, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)

        emit(
            "result",
            requested=REDIRECTOR,
            initial_status=resp.status if resp else None,
            final_url=page.url,
            title=page.title(),
            has_grid=page.locator("#GridViewSessionSeats").count() > 0,
            trace=trace,
            html_excerpt=(page.locator("body").inner_text() or "")[:800],
        )
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
