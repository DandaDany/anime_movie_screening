#!/usr/bin/env python3
from __future__ import annotations

import json

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from fetch_movie_showtimes import (
    VIESHOW_URL,
    html_blocks_with_movie,
    records_from_text_block,
    select_vieshow_location,
)

SHOW_DATE = "2026-09-26"
CASES = [
    {
        "label": "TITAN",
        "code": "MU",
        "aliases": ["惡靈古堡：爆發夜", "惡靈古堡 爆發夜"],
    },
]


def main() -> int:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(VIESHOW_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8000)

        for case in CASES:
            ok, message = select_vieshow_location(page, case["code"])
            if not ok:
                results.append({**case, "ok": False, "error": message})
                continue

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            records = []
            blocks = html_blocks_with_movie(soup, case["aliases"])
            for block in blocks:
                records.extend(
                    records_from_text_block(
                        location_id=1,
                        show_date=SHOW_DATE,
                        text=block.get_text("\n", strip=True),
                        aliases=case["aliases"],
                        source_url=VIESHOW_URL,
                        booking_url=VIESHOW_URL,
                        strict_date_sections=True,
                    )
                )

            unique = []
            seen = set()
            for r in records:
                key = (r.start_time, r.format, r.auditorium, r.language)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(
                    {
                        "time": r.start_time,
                        "format": r.format,
                        "auditorium": r.auditorium,
                        "language": r.language,
                        "raw_text": r.raw_text,
                    }
                )
            results.append(
                {
                    "label": case["label"],
                    "code": case["code"],
                    "ok": True,
                    "block_count": len(blocks),
                    "records": unique,
                }
            )

        context.close()
        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
