from __future__ import annotations

import json
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "seat_return_locations.geojson"
FIXED_NOW_MS = 1790398800000  # 2026-09-26 13:00 Asia/Taipei

SEAT_DATA = {
    "updated_at": "2026-09-26T14:05:00+08:00",
    "preview_count": 1,
    "failure_count": 0,
    "previews": {
        "1:111": {
            "key": "1:111",
            "cinema_code": "1",
            "session_id": "111",
            "movie": "回程測試電影",
            "datetime": "2026-09-27 19:25",
            "cinema": "回程測試威秀",
            "auditorium": "第7廳",
            "available": 1,
            "sold": 1,
            "ordinary_seats": 2,
            "wheelchair": 0,
            "fetched_at": "2026-09-26T14:05:00+08:00",
            "rows": [[
                {"type": "available", "seat": "A01"},
                {"type": "sold", "seat": "A02"}
            ]]
        }
    }
}


def install_routes(page):
    geo = FIXTURE.read_text(encoding="utf-8")
    page.route(
        "**/data/locations.geojson",
        lambda route: route.fulfill(
            status=200,
            content_type="application/geo+json",
            body=geo,
        ),
    )
    page.route(
        "**/data/vieshow_seat_previews.json",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(SEAT_DATA, ensure_ascii=False),
        ),
    )
    page.add_init_script(
        f"""
        (() => {{
          const fixedNow = {FIXED_NOW_MS};
          const NativeDate = Date;
          class FixedDate extends NativeDate {{
            constructor(...args) {{ super(...(args.length ? args : [fixedNow])); }}
            static now() {{ return fixedNow; }}
          }}
          FixedDate.parse = NativeDate.parse;
          FixedDate.UTC = NativeDate.UTC;
          window.Date = FixedDate;
        }})()
        """
    )


def choose_return_context(page, mobile: bool):
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    page.wait_for_function("() => Boolean(window.MuseDiscovery)")
    page.evaluate("window.MuseDiscovery.close()")
    page.wait_for_timeout(250)

    page.locator("#dateChips button[data-date='2026-09-27']").click()
    page.wait_for_timeout(120)
    assert page.locator("#movieSelect").input_value() == "回程測試電影"

    if mobile:
        page.locator("#mSeg button[data-tab='format']").click()

    imax = page.locator("#formatFilterList .filter-option", has_text="IMAX")
    imax.click()
    page.wait_for_timeout(500)
    assert page.locator(".cinema-marker").count() == 1

    if mobile:
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"
        container = page.locator("#mSheetBody")
    else:
        container = page.locator(".leaflet-popup").last
        container.wait_for()

    showtime = container.locator(".st-chip-select", has_text="19:25")
    showtime.click()

    seat_link = container.locator("[data-official-cta]")
    assert seat_link.inner_text() == "座位表入口"
    href = seat_link.get_attribute("href")
    assert href and href.startswith("seat-preview.html?")

    query = parse_qs(urlparse(href).query)
    assert query["movie"] == ["回程測試電影"]
    assert query["date"] == ["2026-09-27"]
    assert query["format"] == ["IMAX"]
    assert query["location"] == ["301"]

    return urljoin("http://127.0.0.1:8765/", href)


def assert_seat_page(page, seat_url: str):
    page.goto(seat_url, wait_until="networkidle")

    notice = page.locator("#notice")
    notice_text = notice.inner_text()
    assert "座位資訊為09/26 14:05更新的資訊，實際可售狀態仍以威秀訂票頁為準。" in notice_text
    assert "官網入口 ↗" in notice_text

    official = notice.locator(".official-entry")
    assert (
        official.get_attribute("href")
        == "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111"
    )

    back = page.locator("#backToMap")
    back_href = back.get_attribute("href")
    assert back_href and "restore=1" in back_href
    assert "movie=%E5%9B%9E%E7%A8%8B%E6%B8%AC%E8%A9%A6%E9%9B%BB%E5%BD%B1" in back_href

    back.click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)


def assert_map_restored(page, mobile: bool):
    discovery = page.locator("#movieDiscovery")
    assert discovery.is_hidden()
    assert discovery.get_attribute("aria-hidden") == "true"

    assert page.locator("#movieSelect").input_value() == "回程測試電影"
    assert page.locator("#dateChips button[data-date='2026-09-27']").get_attribute("aria-pressed") == "true"

    imax = page.locator("#formatFilterList .filter-option", has_text="IMAX")
    assert imax.get_attribute("aria-pressed") == "true"
    assert page.locator(".cinema-marker").count() == 1

    if mobile:
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"
        container = page.locator("#mSheetBody")
    else:
        container = page.locator(".leaflet-popup").last
        container.wait_for()

    text = container.inner_text()
    assert "回程測試威秀" in text
    assert "19:25" in text
    assert "21:40" not in text


def run_case(page, mobile: bool):
    seat_url = choose_return_context(page, mobile)
    assert_seat_page(page, seat_url)
    assert_map_restored(page, mobile)


def main() -> int:
    report = {"errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for mobile, viewport in (
                (False, {"width": 1440, "height": 1000}),
                (True, {"width": 390, "height": 844}),
            ):
                context = browser.new_context(
                    viewport=viewport,
                    timezone_id="Asia/Taipei",
                    is_mobile=mobile,
                    has_touch=mobile,
                )
                page = context.new_page()
                install_routes(page)
                try:
                    run_case(page, mobile)
                except Exception:
                    report["errors"].append({
                        "suite": "mobile" if mobile else "desktop",
                        "traceback": traceback.format_exc(),
                    })
                finally:
                    context.close()
        finally:
            browser.close()

    report["passed"] = not report["errors"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
