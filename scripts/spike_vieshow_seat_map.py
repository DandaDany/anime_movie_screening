#!/usr/bin/env python3
"""A/B the prerequisites for VIESHOW public SessionSeats.

Read-only only. No login, ticket selection, seat click, reservation, checkout, or payment.

Goal: isolate whether SessionSeats needs:
- Referer/navigation context
- homepage cookies
- quick-booking select state
- some combination
"""

from __future__ import annotations

import json
from typing import Callable

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

HOME = "https://www.vscinemas.com.tw/"
BOOKING_URL = (
    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
SEAT_URL = (
    "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
CINEMA = "1|TP"
MOVIE = "HO00017919"
DATE = "2026/09/25"
SESSION_VALUE = "cinemacode=1&txtSessionId=1878613"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def new_context(browser: Browser) -> BrowserContext:
    return browser.new_context(
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        user_agent=UA,
        viewport={"width": 1366, "height": 900},
    )


def safe_cookie_summary(cookies: list[dict]) -> list[dict]:
    return [
        {
            "name": c.get("name"),
            "domain": c.get("domain"),
            "path": c.get("path"),
            "sameSite": c.get("sameSite"),
        }
        for c in cookies
    ]


def attach_seat_request_trace(context: BrowserContext, trace: list[dict]) -> None:
    def on_request(req):
        if "/VoucherTicketing/SessionSeats.aspx" not in req.url:
            return
        try:
            headers = req.all_headers()
        except Exception:
            headers = req.headers
        cookie_header = headers.get("cookie", "")
        cookie_names = sorted(
            {
                part.split("=", 1)[0].strip()
                for part in cookie_header.split(";")
                if "=" in part
            }
        )
        trace.append(
            {
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
                "referer": headers.get("referer"),
                "origin": headers.get("origin"),
                "sec_fetch_site": headers.get("sec-fetch-site"),
                "sec_fetch_mode": headers.get("sec-fetch-mode"),
                "sec_fetch_dest": headers.get("sec-fetch-dest"),
                "cookie_names": cookie_names,
            }
        )

    context.on("request", on_request)


def is_seat_preview(page: Page) -> bool:
    try:
        return (
            page.title() == "威秀影城 - 場次座位預覽"
            and page.locator("#GridViewSessionSeats").count() > 0
        )
    except Exception:
        return False


def seat_counts(page: Page) -> dict:
    if not is_seat_preview(page):
        return {}
    return page.evaluate(
        """() => {
            const grid = document.querySelector('#GridViewSessionSeats');
            const seats = Array.from(
                grid.querySelectorAll('.label[data-toggle="tooltip"][title]')
            );
            const available = seats.filter(el => el.classList.contains('label-info'));
            const sold = seats.filter(el => el.classList.contains('label-danger'));
            const wheelchair = Array.from(
                grid.querySelectorAll('img[src*="wheelchair_available" i]')
            );
            return {
                ordinary: seats.length,
                available: available.length,
                sold: sold.length,
                wheelchair: wheelchair.length
            };
        }"""
    )


def select_quick_booking(page: Page) -> None:
    for name, value in (
        ("cinema", CINEMA),
        ("movie", MOVIE),
        ("date", DATE),
        ("session", SESSION_VALUE),
    ):
        page.locator(f'select[name="{name}"]').select_option(value)
        page.wait_for_timeout(1200)


def record_result(
    label: str,
    page: Page,
    status: int | None,
    trace: list[dict],
    cookies: list[dict],
) -> dict:
    result = {
        "label": label,
        "status": status,
        "final_url": page.url,
        "title": page.title(),
        "success": is_seat_preview(page),
        "seat_counts": seat_counts(page),
        "seat_requests": trace,
        "cookies": safe_cookie_summary(cookies),
    }
    emit("variant", **result)
    return result


def run_goto_variant(
    browser: Browser,
    label: str,
    setup: Callable[[Page], None] | None = None,
    referer: str | None = None,
    copied_cookies: list[dict] | None = None,
) -> tuple[dict, list[dict]]:
    context = new_context(browser)
    if copied_cookies:
        context.add_cookies(copied_cookies)

    trace: list[dict] = []
    attach_seat_request_trace(context, trace)
    page = context.new_page()

    if setup:
        setup(page)

    kwargs = {
        "wait_until": "domcontentloaded",
        "timeout": 60_000,
    }
    if referer:
        kwargs["referer"] = referer

    response = page.goto(SEAT_URL, **kwargs)
    page.wait_for_timeout(1800)
    cookies = context.cookies()
    result = record_result(
        label,
        page,
        response.status if response else None,
        trace,
        cookies,
    )
    context.close()
    return result, cookies


def setup_home(page: Page) -> None:
    page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3500)


def setup_booking(page: Page) -> None:
    page.goto(BOOKING_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2500)


def setup_home_selected(page: Page) -> None:
    setup_home(page)
    select_quick_booking(page)


def run_window_open_variant(
    browser: Browser,
    label: str,
    *,
    select_state: bool,
) -> tuple[dict, list[dict]]:
    context = new_context(browser)
    trace: list[dict] = []
    attach_seat_request_trace(context, trace)
    page = context.new_page()
    setup_home(page)
    if select_state:
        select_quick_booking(page)

    with context.expect_page(timeout=15_000) as popup_info:
        page.evaluate("(url) => window.open(url, '_blank')", SEAT_URL)
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    popup.wait_for_timeout(1800)
    cookies = context.cookies()
    result = record_result(label, popup, None, trace, cookies)
    context.close()
    return result, cookies


def run_injected_anchor_variant(
    browser: Browser,
    label: str,
    *,
    select_state: bool,
) -> tuple[dict, list[dict]]:
    context = new_context(browser)
    trace: list[dict] = []
    attach_seat_request_trace(context, trace)
    page = context.new_page()
    setup_home(page)
    if select_state:
        select_quick_booking(page)

    page.evaluate(
        """(url) => {
            const a = document.createElement('a');
            a.id = 'abSeatAnchor';
            a.href = url;
            a.target = '_blank';
            a.textContent = 'AB seat';
            document.body.appendChild(a);
        }""",
        SEAT_URL,
    )
    with context.expect_page(timeout=15_000) as popup_info:
        page.locator("#abSeatAnchor").click()
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    popup.wait_for_timeout(1800)
    cookies = context.cookies()
    result = record_result(label, popup, None, trace, cookies)
    context.close()
    return result, cookies


def run_official_click(
    browser: Browser,
) -> tuple[dict, list[dict]]:
    context = new_context(browser)
    trace: list[dict] = []
    attach_seat_request_trace(context, trace)
    page = context.new_page()
    setup_home(page)
    select_quick_booking(page)

    href = page.locator("#SessionSeats").get_attribute("href")
    emit("official_link", href=href)

    before_cookies = context.cookies()
    emit("official_pre_click_cookies", cookies=safe_cookie_summary(before_cookies))

    with context.expect_page(timeout=15_000) as popup_info:
        page.locator("#SessionSeats").click()
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded", timeout=60_000)
    popup.wait_for_timeout(1800)

    after_cookies = context.cookies()
    result = record_result(
        "official_click_control",
        popup,
        None,
        trace,
        after_cookies,
    )
    context.close()
    return result, before_cookies


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=40)

        results = []

        r, _ = run_goto_variant(browser, "A_fresh_direct")
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "B_fresh_direct_referer_home",
            referer=HOME,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "C_fresh_direct_referer_booking",
            referer=BOOKING_URL,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "D_home_then_direct",
            setup=setup_home,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "E_booking_then_direct",
            setup=setup_booking,
        )
        results.append(r)

        r, _ = run_window_open_variant(
            browser,
            "F_home_window_open_no_selection",
            select_state=False,
        )
        results.append(r)

        r, _ = run_injected_anchor_variant(
            browser,
            "G_home_anchor_no_selection",
            select_state=False,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "H_home_selected_then_direct",
            setup=setup_home_selected,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "I_home_selected_then_direct_referer_home",
            setup=setup_home_selected,
            referer=HOME,
        )
        results.append(r)

        official, official_pre_click_cookies = run_official_click(browser)
        results.append(official)

        r, _ = run_goto_variant(
            browser,
            "K_fresh_with_preclick_cookies",
            copied_cookies=official_pre_click_cookies,
        )
        results.append(r)

        r, _ = run_goto_variant(
            browser,
            "L_fresh_with_preclick_cookies_referer_home",
            copied_cookies=official_pre_click_cookies,
            referer=HOME,
        )
        results.append(r)

        browser.close()

    emit(
        "summary",
        variants=[
            {
                "label": r["label"],
                "success": r["success"],
                "final_url": r["final_url"],
                "seat_requests": r["seat_requests"],
            }
            for r in results
        ],
        successful=[r["label"] for r in results if r["success"]],
    )

    control = next(r for r in results if r["label"] == "official_click_control")
    return 0 if control["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
