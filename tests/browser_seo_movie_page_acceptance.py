from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"


def find_movie_with_showtimes() -> Path:
    for path in sorted(WEB.glob("movie-*.html")):
        text = path.read_text(encoding="utf-8")
        if 'id="cinemaListPanel"' in text and 'id="map"' in text:
            return path
    raise AssertionError("expected at least one movie page with original map shell")


def block_map_tiles(page) -> None:
    page.route("**/basemaps.cartocdn.com/**", lambda route: route.abort())


def verify_desktop(page, movie_file: str) -> None:
    block_map_tiles(page)
    page.goto(f"http://127.0.0.1:8765/{movie_file}", wait_until="domcontentloaded")

    page.locator("#map.leaflet-container").wait_for(timeout=30000)
    page.wait_for_function("() => Boolean(window.MuseMapIntegration)")
    page.locator("#cinemaList .cinema-list-card").first.wait_for(timeout=30000)

    # Original UI elements remain present and visible.
    assert page.locator(".sidebar").is_visible()
    assert page.locator("#timeSlider").is_visible()
    assert page.locator("#dateChips").count() == 1
    assert page.locator("#cityFilterList").count() == 1
    assert page.locator("#formatFilterList").count() == 1
    assert page.locator("#chainFilterList").count() == 1
    assert page.locator(".map-home-control-button").count() == 1

    # Only the cinema-list column is inserted, with the map still farthest right.
    sidebar = page.locator(".sidebar").bounding_box()
    cinema_list = page.locator("#cinemaListPanel").bounding_box()
    map_wrap = page.locator(".map-wrap").bounding_box()
    assert sidebar and cinema_list and map_wrap
    assert sidebar["x"] < cinema_list["x"] < map_wrap["x"], (sidebar, cinema_list, map_wrap)
    assert map_wrap["x"] + map_wrap["width"] >= 1430, map_wrap

    # The inserted list is driven by the original filter result.
    initial_count = int(page.locator("#cinemaListCount").inner_text())
    assert initial_count > 0

    city_buttons = page.locator("#cityFilterList .filter-option")
    if city_buttons.count() > 1:
        target = city_buttons.nth(0)
        target.click()
        page.wait_for_timeout(100)
        filtered_count = int(page.locator("#cinemaListCount").inner_text())
        assert filtered_count >= 1
        assert filtered_count <= initial_count
        # Click again to clear the original filter.
        target.click()
        page.wait_for_timeout(100)

    # Original markers/popup are still used.
    markers = page.locator(".cinema-marker")
    assert markers.count() > 0
    page.locator(".leaflet-marker-icon").first.click(force=True)
    page.locator(".leaflet-popup:visible").last.wait_for(timeout=5000)
    assert page.locator(".cinema-list-card.is-active").count() == 1

    # Clicking the inserted list delegates to the original map focus behavior.
    first_card = page.locator("#cinemaList .cinema-list-card").first
    first_card.click(position={"x": 8, "y": 8})
    page.locator(".leaflet-popup").wait_for(timeout=5000)

    # Original popup actions are reused inside the list.
    assert page.locator("#cinemaList .popup-links").count() > 0


def verify_mobile(playwright, movie_file: str) -> None:
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            timezone_id="Asia/Taipei",
            locale="zh-TW",
            geolocation={"latitude": 25.0330, "longitude": 121.5654},
            permissions=["geolocation"],
        )
        page = context.new_page()
        block_map_tiles(page)
        page.goto(f"http://127.0.0.1:8765/{movie_file}", wait_until="domcontentloaded")

        page.locator("#map.leaflet-container").wait_for(timeout=30000)
        page.locator("#mSeg").wait_for()

        # Mobile remains the original map + fixed filter tray UX.
        assert page.locator("#cinemaListPanel").is_hidden()
        assert page.locator("#mSeg").is_visible()
        assert page.locator(".sidebar").is_visible()
        assert page.locator("#map").is_visible()
        assert page.locator("#mSheet").count() == 1

        # Original marker click still opens the original mobile cinema sheet.
        marker = page.locator(".leaflet-marker-icon").first
        marker.wait_for(timeout=30000)
        marker.click(force=True)
        page.wait_for_function(
            "() => document.querySelector('.app-shell')?.classList.contains('sheet-open')"
        )
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"
        context.close()
    finally:
        browser.close()


def main() -> int:
    target = find_movie_with_showtimes()
    movie_file = target.name

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            desktop = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                timezone_id="Asia/Taipei",
                locale="zh-TW",
                geolocation={"latitude": 25.0330, "longitude": 121.5654},
                permissions=["geolocation"],
            )
            page = desktop.new_page()
            verify_desktop(page, movie_file)
            desktop.close()
        finally:
            browser.close()

        verify_mobile(playwright, movie_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
