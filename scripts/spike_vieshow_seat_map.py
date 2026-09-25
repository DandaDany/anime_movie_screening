#!/usr/bin/env python3
"""Read-only investigation of VIESHOW VoucherTicketing SessionSeats.

Safety constraints:
- no ticket quantity changes
- no form submissions
- no seat clicks
- no checkout/payment actions
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

CINEMA = "1"
SESSION = "1878613"
BOOKING_URL = (
    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
    f"?cinemacode={CINEMA}&txtSessionId={SESSION}"
)
SEAT_URL = (
    "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
    f"?cinemacode={CINEMA}&txtSessionId={SESSION}"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def summarize_page(page, label: str) -> None:
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""

    interesting_links = page.locator("a[href], form[action], script[src]").evaluate_all(
        """els => els.map(el => ({
            tag: el.tagName,
            href: el.getAttribute('href') || '',
            action: el.getAttribute('action') || '',
            src: el.getAttribute('src') || '',
            text: (el.innerText || el.textContent || '').trim().slice(0, 200)
        })).filter(x => /seat|voucher|ticket|session/i.test(
            [x.href, x.action, x.src, x.text].join(' ')
        )).slice(0, 80)"""
    )

    hidden_inputs = page.locator('input[type="hidden"]').evaluate_all(
        """els => els.map(el => ({
            name: el.name || '',
            id: el.id || '',
            value: (el.value || '').slice(0, 500)
        })).filter(x => /session|cinema|seat|viewstate|eventvalidation|token/i.test(
            [x.name, x.id].join(' ')
        )).slice(0, 100)"""
    )

    seatish = page.locator(
        '[id*="seat" i], [class*="seat" i], [name*="seat" i], '
        'img[src*="seat" i], [id*="chair" i], [class*="chair" i]'
    ).evaluate_all(
        """els => els.slice(0, 100).map(el => ({
            tag: el.tagName,
            id: el.id || '',
            className: typeof el.className === 'string' ? el.className : '',
            name: el.getAttribute('name') || '',
            src: el.getAttribute('src') || '',
            text: (el.innerText || el.textContent || '').trim().slice(0, 250),
            attrs: Object.fromEntries(Array.from(el.attributes || []).map(a => [a.name, a.value]))
        }))"""
    )

    scripts_inline = page.locator("script:not([src])").evaluate_all(
        """els => els.map(el => el.textContent || '')
            .filter(t => /seat|SessionSeats|txtSessionId|cinemacode/i.test(t))
            .map(t => t.slice(0, 5000))
            .slice(0, 20)"""
    )

    emit(
        "page",
        label=label,
        url=page.url,
        title=page.title(),
        body_excerpt=re.sub(r"\s+", " ", body).strip()[:1600],
        interesting_links=interesting_links,
        hidden_inputs=hidden_inputs,
        seatish=seatish,
        inline_scripts=scripts_inline,
    )


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=60)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()

        network = []

        def on_response(resp):
            url = resp.url
            if any(token in url.lower() for token in ("seat", "voucher", "ticket", "session")):
                network.append({
                    "status": resp.status,
                    "url": url,
                    "resource_type": resp.request.resource_type,
                    "method": resp.request.method,
                    "post_data": resp.request.post_data,
                })

        page.on("response", on_response)

        # 1. Direct seat URL in a fresh context.
        response = page.goto(SEAT_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
        emit(
            "navigation",
            phase="fresh_seat",
            requested=SEAT_URL,
            status=response.status if response else None,
            final_url=page.url,
        )
        summarize_page(page, "fresh_seat")
        emit("cookies", phase="fresh_seat", cookies=awaitable_cookie_summary(context.cookies()))

        # 2. Visit the valid booking page, but do NOT choose ticket quantities or submit.
        response = page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
        emit(
            "navigation",
            phase="booking_page",
            requested=BOOKING_URL,
            status=response.status if response else None,
            final_url=page.url,
        )
        summarize_page(page, "booking_page")
        emit("cookies", phase="booking_page", cookies=awaitable_cookie_summary(context.cookies()))

        # 3. Re-open SessionSeats in the SAME context to test whether merely visiting
        #    booking.aspx establishes the required server-side state.
        response = page.goto(SEAT_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)
        emit(
            "navigation",
            phase="seat_after_booking",
            requested=SEAT_URL,
            status=response.status if response else None,
            final_url=page.url,
        )
        summarize_page(page, "seat_after_booking")
        emit("cookies", phase="seat_after_booking", cookies=awaitable_cookie_summary(context.cookies()))

        emit("network", entries=network[-150:])

        context.close()
        browser.close()

    return 0


def awaitable_cookie_summary(cookies: list[dict]) -> list[dict]:
    # Strip values to avoid dumping opaque session secrets to logs.
    return [
        {
            "name": cookie.get("name"),
            "domain": cookie.get("domain"),
            "path": cookie.get("path"),
            "secure": cookie.get("secure"),
            "httpOnly": cookie.get("httpOnly"),
            "sameSite": cookie.get("sameSite"),
            "value_length": len(cookie.get("value") or ""),
        }
        for cookie in cookies
    ]


if __name__ == "__main__":
    raise SystemExit(main())
