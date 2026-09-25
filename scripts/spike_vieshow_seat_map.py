#!/usr/bin/env python3
"""Test a pure-frontend two-hop VIESHOW seat-preview handoff.

Read-only: no login, ticket selection, seat click, reservation, checkout, or payment.
"""

from __future__ import annotations

import json
from playwright.sync_api import sync_playwright

SITE = "https://dandadany.github.io/anime_movie_screening/"
HOME = "https://www.vscinemas.com.tw/"
BOOKING_URL = (
    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
SEAT_URL = (
    "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def run_case(context, label: str, first_url: str):
    opener = context.new_page()
    opener.goto(SITE, wait_until="domcontentloaded", timeout=60_000)
    opener.wait_for_timeout(1500)

    trace = []

    def on_request(req):
        if "SessionSeats.aspx" in req.url:
            headers = req.all_headers()
            trace.append({
                "url": req.url,
                "referer": headers.get("referer"),
                "sec_fetch_site": headers.get("sec-fetch-site"),
                "sec_fetch_mode": headers.get("sec-fetch-mode"),
            })

    context.on("request", on_request)

    with context.expect_page(timeout=15_000) as info:
        opener.evaluate(
            """url => {
                window.__seatPopup = window.open(url, '_blank');
            }""",
            first_url,
        )
    popup = info.value
    popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    popup.wait_for_timeout(1800)

    first_state = {
        "url": popup.url,
        "title": popup.title(),
    }

    # Exactly what our static frontend could do: the opener retains the WindowProxy
    # and navigates that existing tab after the official page has loaded.
    opener.evaluate(
        """url => {
            window.__seatPopup.location.href = url;
        }""",
        SEAT_URL,
    )
    popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    popup.wait_for_timeout(2200)

    result = {
        "label": label,
        "first_state": first_state,
        "final_url": popup.url,
        "title": popup.title(),
        "has_grid": popup.locator("#GridViewSessionSeats").count() > 0,
        "trace": trace,
    }
    emit("case", **result)
    opener.close()
    popup.close()
    return result


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )

        booking = run_case(context, "booking_then_opener_navigate", BOOKING_URL)
        home = run_case(context, "home_then_opener_navigate", HOME)

        context.close()
        browser.close()

    emit(
        "summary",
        booking_success=booking["has_grid"],
        home_success=home["has_grid"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
