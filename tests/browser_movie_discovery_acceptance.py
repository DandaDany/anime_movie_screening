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
    locations_payload["movies"].append(
        {
            "title": "電影 F",
            "show_date": "2026-08-12",
            "available_dates": ["2026-08-12"],
            "feature_count": 1,
        }
    )
    locations_payload["movie_features"]["電影 F"] = []
    locations_payload["movie_features_by_date"]["電影 F"] = {
        "2026-08-12": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.50, 25.03]},
                "properties": {
                    "location_id": 302,
                    "chain_name": "測試影城",
                    "location_name": "台北 F 館",
                    "map_name": "測試影城 台北 F 館",
                    "address": "臺北市測試路8號",
                    "city": "臺北市",
                    "movie_title": "電影 F",
                    "show_date": "2026-08-12",
                    "showtime_count": 1,
                    "showtimes": [
                        {
                            "time": "20:30",
                            "format": "數位",
                            "booking_url": "https://example.test/f302/2030",
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
                    "title": "電影 A：這是一個非常非常長而且需要完整顯示的動畫電影標題",
                    "aliases": ["電影 A"],
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
                    "poster_url": "https://example.com/c-primary.jpg",
                    "poster_fallback_url": "https://example.com/c-fallback.jpg",
                },
                {
                    "id": 4,
                    "title": "電影 D 顯示",
                    "aliases": ["電影 D"],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/d.jpg",
                },
                {
                    "id": 5,
                    "title": "電影 E",
                    "aliases": [],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/e.jpg",
                },
                {
                    "id": 6,
                    "title": "電影 F",
                    "aliases": [],
                    "target_date": "2026-08-01",
                    "poster_url": "https://example.com/f.jpg",
                },
                {
                    "id": 7,
                    "title": "電影 G",
                    "aliases": [],
                    "target_date": "2026-10-01",
                    "poster_url": "https://example.com/g.jpg",
                },
                {
                    "id": 8,
                    "title": "電影 H",
                    "aliases": [],
                    "target_date": "2027-01-29",
                    "poster_url": "https://example.com/h.jpg",
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
    def fulfill_poster(route):
        if route.request.url.endswith("/c-primary.jpg"):
            route.fulfill(status=404, body="missing")
            return
        route.fulfill(
            status=200,
            content_type="image/svg+xml",
            body="<svg xmlns='http://www.w3.org/2000/svg' width='400' height='600'><rect width='400' height='600' fill='#333'/></svg>",
        )

    page.route("https://example.com/*.jpg", fulfill_poster)
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
            assert page.locator("#nowShowingTitle").inner_text() == "正在上映"
            page.locator("#nowShowingGrid .movie-card").first.wait_for()
            # 「正在上映」只保留目前能直接進今天地圖，或至少有其他可進日期的電影。
            # E 完全沒有場次；F 今天最後一場 20:30 已過且沒有未來日期，兩者都不可顯示。
            assert page.locator("#nowShowingGrid .movie-card").count() == 3
            assert page.locator("#nowShowingGrid .movie-card", has_text="電影 E").count() == 0
            assert page.locator("#nowShowingGrid .movie-card", has_text="電影 F").count() == 0
            # 即將上映不再受 lookahead_days=7 限制；10/01 的 G 距今天遠超過 7 天仍必須顯示。
            assert page.locator("#comingSoonGrid .movie-card").count() == 3
            assert page.locator("#comingSoonGrid .movie-card__title").all_text_contents() == ["電影 C", "電影 G", "電影 H"]
            movie_c_poster = page.locator("#comingSoonGrid .movie-card", has_text="電影 C").locator("img")
            page.wait_for_function(
                "(img) => img.complete && img.naturalWidth > 0 && img.dataset.posterFallbackTried === '1'",
                arg=movie_c_poster.element_handle(),
            )
            assert not page.locator("#comingSoonGrid .movie-card", has_text="電影 C").locator(".movie-card__poster").evaluate(
                "el => el.classList.contains('is-missing')"
            )
            assert page.evaluate("document.documentElement.classList.contains('discovery-active')")
            assert page.locator(".sidebar").evaluate("el => getComputedStyle(el).display") == "none"

            # 首頁電影卡現在是獨立頁入口，不再直接切換地圖狀態。
            movie_c = page.locator("#comingSoonGrid .movie-card", has_text="電影 C")
            movie_a = page.locator("#nowShowingGrid .movie-card", has_text="電影 A")
            assert movie_c.get_attribute("href") == "movie-3.html"
            assert movie_a.get_attribute("href") == "movie-1.html"
            assert page.locator("#movieDiscovery").is_visible()

            meta = page.locator(".movie-discovery__meta")
            assert meta.is_visible()
            assert "實際上映與售票狀況請以影城官方資訊為準" in meta.inner_text()
            assert meta.locator('a[href="about.html"]').count() == 1

            first_poster = page.locator("#nowShowingGrid .movie-card__poster").nth(0)
            second_poster = page.locator("#nowShowingGrid .movie-card__poster").nth(1)
            first_poster_box = first_poster.bounding_box()
            second_poster_box = second_poster.bounding_box()
            assert first_poster_box and second_poster_box
            assert abs(first_poster_box["width"] - second_poster_box["width"]) <= 1
            assert abs(first_poster_box["height"] - second_poster_box["height"]) <= 1

            # Desktop hover restores the poster-only zoom without changing the card grid.
            first_poster.hover()
            page.wait_for_timeout(220)
            poster_scale = first_poster.evaluate(
                "el => new DOMMatrix(getComputedStyle(el).transform).a"
            )
            assert poster_scale >= 1.04, poster_scale

            long_title = page.locator("#nowShowingGrid .movie-card", has_text="電影 A").locator(".movie-card__title")
            assert float(long_title.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")) >= 15
            long_metrics = long_title.evaluate(
                """el => ({
                    text: el.textContent,
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    overflow: getComputedStyle(el).overflow,
                    lineClamp: getComputedStyle(el).webkitLineClamp,
                })"""
            )
            assert "非常非常長" in long_metrics["text"]
            assert long_metrics["scrollHeight"] <= long_metrics["clientHeight"] + 1, long_metrics
            assert long_metrics["overflow"] == "visible", long_metrics
            assert long_metrics["lineClamp"] in ("none", ""), long_metrics

            artifact_dir = REPO / "artifacts"
            artifact_dir.mkdir(exist_ok=True)
            page.screenshot(path=str(artifact_dir / "movie-discovery-desktop.png"), full_page=True)
            movie_a.click()
            page.wait_for_url("**/movie-1.html")
            assert page.url.endswith("/movie-1.html")
            context.close()

            # Mobile uses the same discovery homepage/data, with both shelves visible.
            mobile = browser.new_context(
                viewport={"width": 390, "height": 844},
                timezone_id="Asia/Taipei",
                locale="zh-TW",
            )
            mobile_page = mobile.new_page()
            install_fixture(mobile_page)
            mobile_page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
            mobile_page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            mobile_page.locator("#nowShowingGrid .movie-card").first.wait_for()

            assert mobile_page.locator("#movieDiscovery").is_visible()
            assert mobile_page.locator("#nowShowingTitle").inner_text() == "正在上映"
            assert mobile_page.locator("#comingSoonTitle").inner_text() == "即將上映"
            assert mobile_page.locator("#nowShowingGrid .movie-card").count() == 3
            assert mobile_page.locator("#comingSoonGrid .movie-card").count() == 3
            mobile_meta = mobile_page.locator(".movie-discovery__meta")
            assert mobile_meta.is_visible()
            assert mobile_meta.locator('a[href="about.html"]').count() == 1

            # The mobile homepage is genuinely a two-column poster grid, not a hidden desktop overlay.
            first = mobile_page.locator("#nowShowingGrid .movie-card").nth(0).bounding_box()
            second = mobile_page.locator("#nowShowingGrid .movie-card").nth(1).bounding_box()
            assert first and second
            assert abs(first["y"] - second["y"]) < 4, (first, second)
            assert second["x"] > first["x"] + first["width"] * 0.7, (first, second)

            mobile_first_poster = mobile_page.locator("#nowShowingGrid .movie-card__poster").nth(0)
            mobile_second_poster = mobile_page.locator("#nowShowingGrid .movie-card__poster").nth(1)
            mobile_first_box = mobile_first_poster.bounding_box()
            mobile_second_box = mobile_second_poster.bounding_box()
            assert mobile_first_box and mobile_second_box
            assert abs(mobile_first_box["width"] - mobile_second_box["width"]) <= 1
            assert abs(mobile_first_box["height"] - mobile_second_box["height"]) <= 1

            mobile_long_title = mobile_page.locator("#nowShowingGrid .movie-card", has_text="電影 A").locator(".movie-card__title")
            assert float(mobile_long_title.evaluate("el => parseFloat(getComputedStyle(el).fontSize)")) >= 14
            mobile_long_metrics = mobile_long_title.evaluate(
                """el => ({
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    overflow: getComputedStyle(el).overflow,
                    lineClamp: getComputedStyle(el).webkitLineClamp,
                })"""
            )
            assert mobile_long_metrics["scrollHeight"] <= mobile_long_metrics["clientHeight"] + 1, mobile_long_metrics
            assert mobile_long_metrics["overflow"] == "visible", mobile_long_metrics
            assert mobile_long_metrics["lineClamp"] in ("none", ""), mobile_long_metrics

            # With two columns, card 3 starts on the next row. Its poster must not cover
            # the full title under card 1.
            first_title_box = mobile_long_title.bounding_box()
            next_row_poster = mobile_page.locator("#nowShowingGrid .movie-card").nth(2).locator(".movie-card__poster").bounding_box()
            assert first_title_box and next_row_poster
            assert first_title_box["y"] + first_title_box["height"] + 4 <= next_row_poster["y"], (
                first_title_box,
                next_row_poster,
            )

            mobile_movie = mobile_page.locator("#nowShowingGrid .movie-card").first
            mobile_href = mobile_movie.get_attribute("href")
            assert mobile_href and mobile_href.startswith("movie-") and mobile_href.endswith(".html")
            mobile_movie.click()
            mobile_page.wait_for_url(f"**/{mobile_href}")
            assert mobile_page.url.endswith("/" + mobile_href)
            mobile.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
