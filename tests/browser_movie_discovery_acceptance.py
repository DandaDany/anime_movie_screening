from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "multiday_locations.geojson"
FIXED_NOW_MS = 1786538700000  # 2026-08-12 20:45:00 Asia/Taipei


def install_fixture(page):
    locations_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    locations_payload["movies"].append(
        {
            "title": "電影 D",
            "show_date": "2026-08-13",
            "available_dates": ["2026-08-13"],
            "feature_count": 1,
        }
    )
    locations_payload["movie_features"]["電影 D"] = []
    locations_payload["movie_features_by_date"]["電影 D"] = {
        "2026-08-13": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.52, 25.04]},
                "properties": {
                    "location_id": 301,
                    "chain_name": "測試影城",
                    "location_name": "台北 D 館",
                    "map_name": "測試影城 台北 D 館",
                    "address": "臺北市測試路7號",
                    "city": "臺北市",
                    "movie_title": "電影 D",
                    "show_date": "2026-08-13",
                    "showtime_count": 1,
                    "showtimes": [
                        {
                            "time": "19:00",
                            "format": "數位",
                            "booking_url": "https://example.test/d301/1900",
                        }
                    ],
                },
            }
        ]
    }
    locations = json.dumps(locations_payload, ensure_ascii=False)
    discovery = json.dumps(
        {
            "schema_version": 1,
            "lookahead_days": 7,
            "movies": [
                {
                    "id": 1,
                    "title": "電影 A",
                    "aliases": [],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/a.jpg",
                },
                {
                    "id": 2,
                    "title": "電影 B",
                    "aliases": [],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/b.jpg",
                },
                {
                    "id": 3,
                    "title": "電影 C",
                    "aliases": [],
                    "target_date": "2026-08-13",
                    "poster_url": "https://example.com/c.jpg",
                },
                {
                    "id": 4,
                    "title": "電影 D 顯示",
                    "aliases": ["電影 D"],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/d.jpg",
                },
            ],
        },
        ensure_ascii=False,
    )
    page.route(
        "**/data/locations.geojson",
        lambda route: route.fulfill(status=200, content_type="application/geo+json", body=locations),
    )
    page.route(
        "**/data/movie_discovery.json",
        lambda route: route.fulfill(status=200, content_type="application/json", body=discovery),
    )
    page.route(
        "https://example.com/*.jpg",
        lambda route: route.fulfill(
            status=200,
            content_type="image/svg+xml",
            body="<svg xmlns='http://www.w3.org/2000/svg' width='400' height='600'><rect width='400' height='600' fill='#333'/></svg>",
        ),
    )
    page.add_init_script(
        f"""
        (() => {{
          const fixedNow = {FIXED_NOW_MS};
          window.__TEST_NOW_MS = fixedNow;
          const NativeDate = Date;
          class FixedDate extends NativeDate {{
            constructor(...args) {{ super(...(args.length ? args : [window.__TEST_NOW_MS])); }}
            static now() {{ return window.__TEST_NOW_MS; }}
          }}
          FixedDate.parse = NativeDate.parse;
          FixedDate.UTC = NativeDate.UTC;
          window.Date = FixedDate;
        }})()
        """,
    )


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                timezone_id="Asia/Taipei",
            )
            page = context.new_page()
            install_fixture(page)
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle")

            page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            page.locator("#nowShowingGrid .movie-card").first.wait_for()
            # "正在上映" follows the canonical tracked-movie feed, not today's remaining-showtime options.
            assert page.locator("#nowShowingGrid .movie-card").count() == 3
            assert page.locator("#comingSoonGrid .movie-card").count() == 1
            assert page.locator("#comingSoonGrid .movie-card__title").inner_text() == "電影 C"
            assert page.evaluate("document.documentElement.classList.contains('discovery-active')")
            assert page.locator(".sidebar").evaluate("el => getComputedStyle(el).display") == "none"

            page.locator("#comingSoonGrid .movie-card").click()
            page.locator("#movieDiscoveryToast").filter(has_text="尚未有上映資訊").wait_for()

            # 電影 B 今天最後一場 20:30，固定現在時間 20:45；卡片仍留在「正在上映」。
            page.locator("#nowShowingGrid .movie-card", has_text="電影 B").click()
            dialog = page.locator("#movieNoTodayDialog")
            dialog.wait_for()
            assert "今日剩餘場次已結束" in dialog.inner_text()
            assert "是否看其他日期？" in dialog.inner_text()

            # 否：關閉 dialog，留在選片頁。
            page.locator("#movieNoTodayNo").click()
            assert dialog.is_hidden()
            assert page.locator("#movieDiscovery").is_visible()

            # 是：自動找到電影 B 的其他有場次日期（8/15）並進入地圖。
            page.locator("#nowShowingGrid .movie-card", has_text="電影 B").click()
            dialog.wait_for()
            page.locator("#movieNoTodayYes").click()
            page.wait_for_function("() => !document.documentElement.classList.contains('discovery-active')")
            assert page.locator("#movieSelect").input_value() == "電影 B"
            assert page.locator("#dateChips .date-chip.is-selected").get_attribute("data-date") == "2026-08-15"
            assert page.locator("#movieDiscovery").is_hidden()

            # 電影 D 今天沒有排映，但明天有場次；不能誤說成「沒有上映」。
            page.locator(".map-home-control-button").click()
            page.wait_for_function("() => document.documentElement.classList.contains('discovery-active')")
            page.locator("#nowShowingGrid .movie-card", has_text="電影 D 顯示").click()
            dialog.wait_for()
            assert "今天沒有排映場次" in dialog.inner_text()
            assert "是否看其他日期？" in dialog.inner_text()
            page.locator("#movieNoTodayYes").click()
            page.wait_for_function("() => !document.documentElement.classList.contains('discovery-active')")
            assert page.locator("#movieSelect").input_value() == "電影 D"
            assert page.locator("#dateChips .date-chip.is-selected").get_attribute("data-date") == "2026-08-13"

            # Home 回選片後，電影 A 今天 21:00 尚有場次，應直接回到今天地圖、不跳 dialog。
            page.locator(".map-home-control-button").click()
            page.wait_for_function("() => document.documentElement.classList.contains('discovery-active')")
            assert page.locator("#movieDiscovery").is_visible()
            page.locator("#nowShowingGrid .movie-card", has_text="電影 A").click()
            page.wait_for_function("() => !document.documentElement.classList.contains('discovery-active')")
            assert page.locator("#movieSelect").input_value() == "電影 A"
            assert page.locator("#dateChips .date-chip.is-selected").get_attribute("data-date") == "2026-08-12"
            assert dialog.is_hidden()

            page.locator(".map-home-control-button").click()
            page.wait_for_function("() => document.documentElement.classList.contains('discovery-active')")
            assert page.locator("#movieDiscovery").is_visible()

            artifact_dir = REPO / "artifacts"
            artifact_dir.mkdir(exist_ok=True)
            page.screenshot(path=str(artifact_dir / "movie-discovery-desktop.png"), full_page=True)
            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
