#!/usr/bin/env python3
"""Final VIESHOW direct-link comparison using live session IDs discovered 2026-09-25.

No seat reservation or purchase is performed.
"""
from __future__ import annotations
import json
import re
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
LIVE = [
    ("台北信義威秀影城", "1", "1878470"),
    ("MUVIE CINEMAS 台北松仁", "21", "165732"),
    ("高雄大遠百威秀影城", "6", "1851952"),
]
URLS = {
    "official_booking": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode={cinema}&txtSessionId={session}",
    "voucher_session_seats": "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx?cinemacode={cinema}&txtSessionId={session}",
}


def emit(event, **data):
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def ctx(browser):
    return browser.new_context(
        locale="zh-TW", timezone_id="Asia/Taipei", user_agent=UA,
        viewport={"width": 1366, "height": 900}
    )


def check(browser, label, cinema, session, kind, template):
    c = ctx(browser)
    p = c.new_page()
    url = template.format(cinema=cinema, session=session)
    try:
        response = p.goto(url, wait_until="domcontentloaded", timeout=25_000)
        p.wait_for_timeout(3500)
        body = p.locator("body").inner_text(timeout=5000)
        out = {
            "label": label,
            "cinemacode": cinema,
            "session_id": session,
            "kind": kind,
            "requested_url": url,
            "status": response.status if response else None,
            "final_url": p.url,
            "title": p.title(),
            "stayed_on_booking": "/vsticketing/ticketing/booking.aspx" in p.url.lower(),
            "stayed_on_session_seats": "/voucherticketing/sessionseats.aspx" in p.url.lower(),
            "redirected_home": p.url.rstrip("/") == "https://www.vscinemas.com.tw",
            "body_excerpt": re.sub(r"\s+", " ", body).strip()[:900],
            "error": None,
        }
    except Exception as exc:
        out = {
            "label": label, "cinemacode": cinema, "session_id": session,
            "kind": kind, "requested_url": url, "status": None,
            "final_url": p.url, "error": f"{type(exc).__name__}: {exc}",
        }
    emit("link_check", **out)
    c.close()
    return out


def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=80)
        for label, cinema, session in LIVE:
            for kind, template in URLS.items():
                results.append(check(browser, label, cinema, session, kind, template))
        browser.close()

    emit(
        "summary",
        tests=len(results),
        official_booking_success=sum(
            bool(r.get("stayed_on_booking")) and not r.get("redirected_home")
            for r in results if r.get("kind") == "official_booking"
        ),
        official_booking_total=sum(r.get("kind") == "official_booking" for r in results),
        voucher_seat_success=sum(
            bool(r.get("stayed_on_session_seats")) and not r.get("redirected_home")
            for r in results if r.get("kind") == "voucher_session_seats"
        ),
        voucher_seat_total=sum(r.get("kind") == "voucher_session_seats" for r in results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
