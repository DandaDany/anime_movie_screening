#!/usr/bin/env python3
"""Trace VIESHOW's public homepage '查看座位' flow for one Session ID.

Read-only:
- no login
- no ticket quantity selection
- no seat click
- no form submission that reserves anything
"""

from __future__ import annotations

import json
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

CINEMA_SHORT = "TP"
CINEMA_VALUE = "1|TP"
TARGET_SESSION = "1878613"
HOME = "https://www.vscinemas.com.tw/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def new_context(browser):
    return browser.new_context(
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        user_agent=UA,
        viewport={"width": 1366, "height": 900},
    )


def find_target_session(page):
    return page.evaluate(
        """async ({cinema, targetSession}) => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const j = async (url) => {
                const r = await fetch(url, {headers: {'Accept': 'application/json,text/plain,*/*'}});
                if (!r.ok) throw new Error(r.status + ' ' + url);
                return await r.json();
            };
            const val = item => String(
                item?.strValue ?? item?.value ?? item?.Value ?? ''
            ).trim();
            const txt = item => String(
                item?.strText ?? item?.text ?? item?.Text ?? ''
            ).trim();

            const movies = await j('/api/GetLstDicMovie?cinema=' + encodeURIComponent(cinema));
            for (const movie of movies || []) {
                const movieValue = val(movie);
                if (!movieValue) continue;
                const dates = await j(
                    '/api/GetLstDicDate?cinema=' + encodeURIComponent(cinema) +
                    '&movie=' + encodeURIComponent(movieValue)
                );
                for (const date of dates || []) {
                    const dateValue = val(date) || txt(date);
                    if (!dateValue) continue;
                    const sessions = await j(
                        '/api/GetLstDicSession?cinema=' + encodeURIComponent(cinema) +
                        '&movie=' + encodeURIComponent(movieValue) +
                        '&date=' + encodeURIComponent(dateValue)
                    );
                    for (const session of sessions || []) {
                        const sessionValue = val(session);
                        if (sessionValue.includes('txtSessionId=' + targetSession)) {
                            return {
                                movieValue,
                                movieText: txt(movie),
                                dateValue,
                                dateText: txt(date),
                                sessionValue,
                                sessionText: txt(session)
                            };
                        }
                    }
                }
                await sleep(30);
            }
            return null;
        }""",
        {"cinema": CINEMA_VALUE, "targetSession": TARGET_SESSION},
    )


def page_summary(page, label):
    try:
        body = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body = ""

    seatish = page.locator(
        '[id*="seat" i], [class*="seat" i], [name*="seat" i], '
        'img[src*="seat" i], [id*="chair" i], [class*="chair" i], '
        '[data-seat], [data-seat-id]'
    ).evaluate_all(
        """els => els.slice(0, 500).map(el => ({
            tag: el.tagName,
            id: el.id || '',
            className: typeof el.className === 'string' ? el.className : '',
            name: el.getAttribute('name') || '',
            src: el.getAttribute('src') || '',
            text: (el.innerText || el.textContent || '').trim().slice(0, 200),
            attrs: Object.fromEntries(Array.from(el.attributes || []).map(a => [a.name, a.value]))
        }))"""
    )

    images = page.locator("img").evaluate_all(
        """els => els.map(el => ({
            src: el.src || '',
            alt: el.alt || '',
            id: el.id || '',
            className: typeof el.className === 'string' ? el.className : ''
        })).filter(x => /seat|chair|screen|session/i.test(
            [x.src, x.alt, x.id, x.className].join(' ')
        )).slice(0, 200)"""
    )

    scripts = page.locator("script:not([src])").evaluate_all(
        """els => els.map(el => el.textContent || '')
          .filter(t => /seat|chair|SessionSeats|GetSeat|sold|available/i.test(t))
          .map(t => t.slice(0, 12000))
          .slice(0, 30)"""
    )

    emit(
        "page_summary",
        label=label,
        url=page.url,
        title=page.title(),
        body_excerpt=re.sub(r"\s+", " ", body).strip()[:2500],
        seatish_count=len(seatish),
        seatish=seatish[:180],
        images=images,
        inline_scripts=scripts,
    )


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        context = new_context(browser)
        page = context.new_page()

        network = []

        def on_response(resp):
            url = resp.url
            low = url.lower()
            if any(k in low for k in ("seat", "session", "ticket", "voucher", "chair")):
                network.append({
                    "status": resp.status,
                    "method": resp.request.method,
                    "resource_type": resp.request.resource_type,
                    "url": url,
                    "post_data": resp.request.post_data,
                })

        context.on("response", on_response)

        page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(5000)

        match = find_target_session(page)
        emit("session_match", match=match)
        if not match:
            context.close()
            browser.close()
            return 2

        # Reproduce the public Quick Booking UI state.
        page.locator('select[name="cinema"]').select_option(CINEMA_VALUE)
        page.wait_for_timeout(1800)
        page.locator('select[name="movie"]').select_option(match["movieValue"])
        page.wait_for_timeout(1800)
        page.locator('select[name="date"]').select_option(match["dateValue"])
        page.wait_for_timeout(1800)
        page.locator('select[name="session"]').select_option(match["sessionValue"])
        page.wait_for_timeout(1200)

        seat_link = page.locator("#SessionSeats")
        link_state = seat_link.evaluate(
            """el => ({
                href: el.getAttribute('href') || '',
                target: el.getAttribute('target') || '',
                onclick: el.getAttribute('onclick') || '',
                outerHTML: el.outerHTML
            })"""
        )
        emit("seat_link_state", **link_state)

        # Public '查看座位' opens a new tab/window. Observe exactly what it opens.
        popup = None
        try:
            with context.expect_page(timeout=15000) as popup_info:
                seat_link.click()
            popup = popup_info.value
            popup.wait_for_load_state("domcontentloaded", timeout=60_000)
            popup.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            emit("popup", opened=False, current_page=page.url)

        if popup:
            emit("popup", opened=True, url=popup.url, title=popup.title())
            page_summary(popup, "public_seat_popup")

        emit("network", entries=network[-250:])

        context.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
