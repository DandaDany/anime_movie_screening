#!/usr/bin/env python3
"""Count VIESHOW public seat-preview availability for one known live session.

Read-only: no login, ticket selection, seat click, reservation, checkout, or payment.
"""

from __future__ import annotations

import json
from playwright.sync_api import sync_playwright

HOME = "https://www.vscinemas.com.tw/"
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


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4000)

        for name, value in (
            ("cinema", CINEMA),
            ("movie", MOVIE),
            ("date", DATE),
            ("session", SESSION_VALUE),
        ):
            page.locator(f'select[name="{name}"]').select_option(value)
            page.wait_for_timeout(1200)

        seat_link = page.locator("#SessionSeats")
        with ctx.expect_page(timeout=15000) as info:
            seat_link.click()
        popup = info.value
        popup.wait_for_load_state("domcontentloaded", timeout=60_000)
        popup.wait_for_timeout(2200)

        result = popup.evaluate(
            """() => {
                const grid = document.querySelector('#GridViewSessionSeats');
                const seatNodes = Array.from(grid.querySelectorAll('.label[data-toggle="tooltip"][title]'));
                const availableNodes = seatNodes.filter(el => el.classList.contains('label-info'));
                const soldNodes = seatNodes.filter(el => el.classList.contains('label-danger'));
                const wheelchairNodes = Array.from(
                    grid.querySelectorAll('img[src*="wheelchair_available" i]')
                );
                const nullNodes = Array.from(
                    grid.querySelectorAll('img[src*="Null.png" i]')
                );

                const getIds = els => els.map(el => el.getAttribute('title')).filter(Boolean);

                const movie = document.querySelector('#LabelMovie_strName')?.textContent?.trim() || '';
                const datetime = document.querySelector('#LabelSession_dtmDateTime')?.textContent?.trim() || '';
                const cinema = document.querySelector('#LabelCinema_strName')?.textContent?.trim() || '';
                const auditorium = document.querySelector('#LabelScreen_strName')?.textContent?.trim() || '';

                return {
                    movie,
                    datetime,
                    cinema,
                    auditorium,
                    available_count: availableNodes.length,
                    sold_count: soldNodes.length,
                    ordinary_seat_count: seatNodes.length,
                    wheelchair_count: wheelchairNodes.length,
                    null_gap_count: nullNodes.length,
                    physical_positions_count: seatNodes.length + wheelchairNodes.length,
                    occupancy_ratio_ordinary:
                        seatNodes.length ? soldNodes.length / seatNodes.length : null,
                    available_ratio_ordinary:
                        seatNodes.length ? availableNodes.length / seatNodes.length : null,
                    sold_seats: getIds(soldNodes),
                    available_seats: getIds(availableNodes)
                };
            }"""
        )

        emit(
            "seat_count",
            seat_url=popup.url,
            title=popup.title(),
            **result,
        )

        ctx.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
