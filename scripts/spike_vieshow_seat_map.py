#!/usr/bin/env python3
"""Read-only / non-reserving investigation of VIESHOW VoucherTicketing seat map.

The script may enter the VoucherTicketing ticket-selection page to establish the
server session, but it never selects a ticket quantity, clicks a seat, reserves,
checks out, or pays.
"""

from __future__ import annotations

import json
import re

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


def cookie_summary(cookies: list[dict]) -> list[dict]:
    return [
        {
            "name": c.get("name"),
            "domain": c.get("domain"),
            "path": c.get("path"),
            "secure": c.get("secure"),
            "httpOnly": c.get("httpOnly"),
            "sameSite": c.get("sameSite"),
            "value_length": len(c.get("value") or ""),
        }
        for c in cookies
    ]


def summarize_page(page, label: str) -> None:
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""

    forms = page.locator("form").evaluate_all(
        """forms => forms.map((f, index) => ({
            index,
            action: f.action || '',
            method: f.method || '',
            controls: Array.from(f.elements || []).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                value: (el.value || '').slice(0, 400),
                checked: 'checked' in el ? !!el.checked : null,
                disabled: !!el.disabled,
                text: (el.innerText || el.textContent || '').trim().slice(0, 150)
            })).slice(0, 120)
        })).filter(f => /voucher|ticket|seat|selecttickets/i.test(f.action))"""
    )

    seatish = page.locator(
        '[id*="seat" i], [class*="seat" i], [name*="seat" i], '
        'img[src*="seat" i], [id*="chair" i], [class*="chair" i]'
    ).evaluate_all(
        """els => els.slice(0, 300).map(el => ({
            tag: el.tagName,
            id: el.id || '',
            className: typeof el.className === 'string' ? el.className : '',
            name: el.getAttribute('name') || '',
            src: el.getAttribute('src') || '',
            value: (el.getAttribute('value') || '').slice(0, 300),
            text: (el.innerText || el.textContent || '').trim().slice(0, 250),
            attrs: Object.fromEntries(Array.from(el.attributes || []).map(a => [a.name, a.value]))
        }))"""
    )

    inline_scripts = page.locator("script:not([src])").evaluate_all(
        """els => els.map(el => el.textContent || '')
            .filter(t => /seat|SessionSeats|SelectTickets|txtSessionId|cinemacode/i.test(t))
            .map(t => t.slice(0, 8000))
            .slice(0, 30)"""
    )

    emit(
        "page",
        label=label,
        url=page.url,
        title=page.title(),
        body_excerpt=re.sub(r"\s+", " ", body).strip()[:2200],
        forms=forms,
        seatish_count=len(seatish),
        seatish=seatish[:120],
        inline_scripts=inline_scripts,
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
            u = resp.url.lower()
            if any(token in u for token in ("seat", "voucher", "ticket", "session", "order")):
                network.append({
                    "status": resp.status,
                    "url": resp.url,
                    "resource_type": resp.request.resource_type,
                    "method": resp.request.method,
                    "post_data": resp.request.post_data,
                })

        page.on("response", on_response)

        # A. Valid booking page.
        resp = page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)
        emit(
            "navigation",
            phase="booking",
            requested=BOOKING_URL,
            status=resp.status if resp else None,
            final_url=page.url,
        )
        summarize_page(page, "booking")
        emit("cookies", phase="booking", cookies=cookie_summary(context.cookies()))

        # B. Enter VoucherTicketing SelectTickets using the existing official form.
        # This establishes the sales-domain application session, but chooses no tickets.
        form = page.locator('form[action*="VoucherTicketing/SelectTickets.aspx"]').first
        if form.count() == 0:
            emit("selecttickets", passed=False, reason="VoucherTicketing form not found")
            context.close()
            browser.close()
            return 2

        controls = form.evaluate(
            """f => Array.from(f.elements || []).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                value: el.value || '',
                checked: 'checked' in el ? !!el.checked : null
            }))"""
        )
        emit("voucher_form_controls", controls=controls)

        # Check only the agreement control if present. Do not touch any ticket quantity.
        form.locator('input[name="agree"]').evaluate_all(
            """els => els.forEach(el => {
                if (el.type === 'checkbox' || el.type === 'radio') el.checked = true;
            })"""
        )

        # Native form.submit(): POST the official fields exactly as the form defines them.
        # This is the transition to ticket selection, not a reservation.
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
            form.evaluate("f => f.submit()")
        page.wait_for_timeout(2500)

        emit(
            "selecttickets",
            passed=True,
            final_url=page.url,
            title=page.title(),
        )
        summarize_page(page, "selecttickets")
        emit("cookies", phase="selecttickets", cookies=cookie_summary(context.cookies()))

        # C. Without changing any ticket quantity, try the user's SessionSeats URL.
        resp = page.goto(SEAT_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2500)
        emit(
            "navigation",
            phase="seat_after_selecttickets",
            requested=SEAT_URL,
            status=resp.status if resp else None,
            final_url=page.url,
        )
        summarize_page(page, "seat_after_selecttickets")
        emit("cookies", phase="seat_after_selecttickets", cookies=cookie_summary(context.cookies()))
        emit("network", entries=network[-180:])

        context.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
