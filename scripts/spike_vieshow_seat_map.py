#!/usr/bin/env python3
"""Inspect VIESHOW public seat-preview markup for one known live session.

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
        browser = p.chromium.launch(headless=False, slow_mo=60)
        ctx = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=UA,
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4500)

        for name, value in (
            ("cinema", CINEMA),
            ("movie", MOVIE),
            ("date", DATE),
            ("session", SESSION_VALUE),
        ):
            page.locator(f'select[name="{name}"]').select_option(value)
            page.wait_for_timeout(1300)

        seat_link = page.locator("#SessionSeats")
        emit(
            "seat_link",
            href=seat_link.get_attribute("href"),
            text=seat_link.inner_text(),
        )

        with ctx.expect_page(timeout=15000) as info:
            seat_link.click()
        popup = info.value
        popup.wait_for_load_state("domcontentloaded", timeout=60_000)
        popup.wait_for_timeout(2500)

        analysis = popup.locator("#GridViewSessionSeats").evaluate(
            """table => {
                const sigMap = new Map();
                const rows = Array.from(table.querySelectorAll('tr')).map((tr, r) => ({
                    row: r,
                    cells: Array.from(tr.querySelectorAll('td')).map((td, c) => {
                        const div = td.querySelector('.DivSeat');
                        const img = td.querySelector('img');
                        const target = div || td;
                        const cs = getComputedStyle(target);
                        const cell = {
                            col: c,
                            text: (td.innerText || td.textContent || '').trim(),
                            tdClass: td.className || '',
                            tdStyle: td.getAttribute('style') || '',
                            divClass: div?.className || '',
                            divStyle: div?.getAttribute('style') || '',
                            imgSrc: img?.src || '',
                            imgAlt: img?.alt || '',
                            imgTitle: img?.title || '',
                            title: td.title || div?.title || '',
                            bgImage: cs.backgroundImage || '',
                            bgColor: cs.backgroundColor || '',
                            color: cs.color || '',
                            html: td.innerHTML.slice(0, 900)
                        };
                        const key = JSON.stringify({
                            tdClass: cell.tdClass,
                            divClass: cell.divClass,
                            imgSrc: cell.imgSrc,
                            imgAlt: cell.imgAlt,
                            bgImage: cell.bgImage,
                            bgColor: cell.bgColor,
                            html: cell.html
                                .replace(/>[A-Z]</g, '>ROW<')
                                .replace(/\s+/g, ' ')
                                .slice(0, 500)
                        });
                        sigMap.set(key, {
                            count: (sigMap.get(key)?.count || 0) + 1,
                            sample: cell
                        });
                        return cell;
                    })
                }));
                const allImgs = Array.from(document.images).map(img => ({
                    src: img.src || '',
                    alt: img.alt || '',
                    title: img.title || '',
                    className: img.className || ''
                }));
                const imageCounts = {};
                for (const img of allImgs) {
                    const key = JSON.stringify(img);
                    imageCounts[key] = (imageCounts[key] || 0) + 1;
                }
                return {
                    rowCount: rows.length,
                    cellCount: rows.reduce((n, r) => n + r.cells.length, 0),
                    signatures: Array.from(sigMap.values())
                        .sort((a,b) => b.count - a.count)
                        .slice(0, 40),
                    imageCounts,
                    firstRows: rows.slice(0, 4)
                };
            }"""
        )

        legend = popup.locator("body").evaluate(
            """body => Array.from(body.querySelectorAll('*')).filter(el => {
                const t = (el.innerText || el.textContent || '').trim();
                return t === '已售出' || /輪椅位/.test(t) || /可售|可選|available|sold/i.test(t);
            }).slice(0, 50).map(el => ({
                tag: el.tagName,
                text: (el.innerText || el.textContent || '').trim(),
                className: typeof el.className === 'string' ? el.className : '',
                html: el.outerHTML.slice(0, 1200)
            }))"""
        )

        emit(
            "seat_markup",
            url=popup.url,
            title=popup.title(),
            analysis=analysis,
            legend=legend,
        )

        ctx.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
