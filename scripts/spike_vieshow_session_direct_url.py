#!/usr/bin/env python3
"""Live acceptance for VIESHOW per-session booking URLs.

Validates five different VIESHOW cinemas with five different live movies:
- discover a unique movie via the official quick-booking API;
- resolve live sessions through the crawler helper;
- open the generated booking.aspx URL in a fresh context;
- require all five to stay on the correct VIESHOW booking page.

No reservation, seat hold, or purchase is performed.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_movie_showtimes as crawler
from playwright.sync_api import sync_playwright

TARGETS = [
    ("TP", "台北信義威秀影城"),
    ("TY", "桃園統領威秀影城"),
    ("HS", "新竹大遠百威秀影城"),
    ("TZ", "台中大遠百威秀影城"),
    ("KS", "高雄大遠百威秀影城"),
]

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


def cinema_value(page, short_code: str) -> str:
    items = crawler._vieshow_api_json(page, "/api/GetLstDicCinema")
    for item in items if isinstance(items, list) else []:
        value = crawler._vieshow_item_value(item)
        parts = value.split("|", 1)
        if len(parts) == 2 and parts[1].strip() == short_code:
            return value
    return ""


def pick_unique_movie(page, short_code: str, used_movies: set[str]):
    value = cinema_value(page, short_code)
    if not value:
        return None

    path = "/api/GetLstDicMovie?" + urllib.parse.urlencode(
        {"cinema": value},
        safe="|",
    )
    items = crawler._vieshow_api_json(page, path)

    for item in items if isinstance(items, list) else []:
        movie_text = crawler._vieshow_item_text(item)
        signature = crawler.normalize_text(movie_text)
        if not movie_text or not signature or signature in used_movies:
            continue

        sessions = crawler._vieshow_quick_booking_sessions(
            page,
            short_code,
            [movie_text],
        )
        if sessions:
            return movie_text, sessions[0]
    return None


def check_booking_url(browser, url: str) -> dict:
    ctx = new_context(browser)
    page = ctx.new_page()
    try:
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        page.wait_for_timeout(2500)
        result = {
            "status": response.status if response else None,
            "final_url": page.url,
            "title": page.title(),
            "booking_page": (
                "/vsticketing/ticketing/booking.aspx"
                in page.url.lower()
                and page.title() == "威秀影城 - 訂票"
            ),
        }
    except Exception as exc:
        result = {
            "status": None,
            "final_url": page.url,
            "title": "",
            "booking_page": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        ctx.close()
    return result


def main() -> int:
    cases = []
    used_movies: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=60)

        source_ctx = new_context(browser)
        source_page = source_ctx.new_page()
        source_page.goto(
            crawler.VIESHOW_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        source_page.wait_for_timeout(5000)

        html = source_page.content()
        if "Access Denied" in html or "queue-it" in f"{source_page.url}\n{html}".lower():
            raise RuntimeError("VIESHOW source blocked during five-cinema acceptance")

        for short_code, cinema_name in TARGETS:
            picked = pick_unique_movie(source_page, short_code, used_movies)
            if not picked:
                emit(
                    "case",
                    cinema=cinema_name,
                    short_code=short_code,
                    passed=False,
                    reason="no unique movie with live session found",
                )
                continue

            movie_text, session = picked
            used_movies.add(crawler.normalize_text(movie_text))
            url = session["booking_url"]
            check = check_booking_url(browser, url)

            case = {
                "cinema": cinema_name,
                "short_code": short_code,
                "movie": movie_text,
                "show_date": session["show_date"],
                "start_time": session["start_time"],
                "booking_url": url,
                **check,
            }
            case["passed"] = bool(check.get("booking_page"))
            cases.append(case)
            emit("case", **case)

        source_ctx.close()
        browser.close()

    passed = [case for case in cases if case.get("passed")]
    distinct_movies = {
        crawler.normalize_text(case["movie"])
        for case in passed
    }
    success = len(passed) == 5 and len(distinct_movies) == 5
    emit(
        "summary",
        total_cases=len(cases),
        passed=len(passed),
        distinct_movies=len(distinct_movies),
        success=success,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
