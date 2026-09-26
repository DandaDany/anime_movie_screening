from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
FIXED_NOW_MS = 1790439300000  # 2026-09-27 00:15 Asia/Taipei
BOOKING_URL = "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27"

LOCATIONS = {
    "type": "FeatureCollection",
    "name": "ShowTimes booking acceptance",
    "show_date": "2026-09-27",
    "updated_at": "2026-09-27T00:10:00+08:00",
    "available_dates": ["2026-09-27"],
    "movies": [
        {
            "title": "劇場版 吉伊卡哇 人魚島的秘密",
            "show_date": "2026-09-27",
            "available_dates": ["2026-09-27"],
            "feature_count": 1,
        }
    ],
    "movie_features": {
        "劇場版 吉伊卡哇 人魚島的秘密": []
    },
    "movie_features_by_date": {
        "劇場版 吉伊卡哇 人魚島的秘密": {
            "2026-09-27": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [121.561, 25.041]},
                    "properties": {
                        "location_id": 991,
                        "chain_name": "秀泰影城",
                        "location_name": "大巨蛋秀泰影城",
                        "map_name": "秀泰 大巨蛋",
                        "address": "臺北市測試地址",
                        "city": "臺北市",
                        "location_url": "https://www.showtimes.com.tw/ticketing?cid=91&date=2026-09-27&category=popular",
                        "official_url": "https://www.showtimes.com.tw/",
                        "movie_title": "劇場版 吉伊卡哇 人魚島的秘密",
                        "show_date": "2026-09-27",
                        "showtime_count": 1,
                        "showtimes": [
                            {
                                "time": "10:10",
                                "format": "數位",
                                "language": "日語",
                                "auditorium": "1廳",
                                "booking_url": BOOKING_URL,
                                "label": "10:10 數位 / 1廳",
                            }
                        ],
                        "start_times": "10:10",
                    },
                }
            ]
        }
    },
    "features": [],
}


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                timezone_id="Asia/Taipei",
            )
            page = context.new_page()
            page.route(
                "**/data/locations.geojson",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/geo+json",
                    body=json.dumps(LOCATIONS, ensure_ascii=False),
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

            page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            page.evaluate("window.MuseDiscovery.close()")
            page.wait_for_timeout(250)

            assert page.locator("#movieSelect").input_value() == "劇場版 吉伊卡哇 人魚島的秘密"
            marker = page.locator(".cinema-marker")
            assert marker.count() == 1
            marker.dispatch_event("click")

            popup = page.locator(".leaflet-popup").last
            popup.wait_for()
            showtime = popup.locator(".st-chip-select", has_text="10:10")
            assert showtime.count() == 1
            assert showtime.get_attribute("aria-pressed") == "false"

            showtime.dispatch_event("click")
            assert showtime.get_attribute("aria-pressed") == "true"

            cta = popup.locator("[data-booking-cta]")
            assert cta.inner_text() == "前往訂票"
            assert cta.get_attribute("href") == BOOKING_URL
            assert cta.get_attribute("aria-disabled") == "false"

            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
