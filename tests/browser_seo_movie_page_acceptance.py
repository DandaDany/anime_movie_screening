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

    # Original UI remains.
    assert page.locator(".sidebar").is_visible()
    assert page.locator("#timeSlider").is_visible()
    assert page.locator("#dateChips").count() == 1
    assert page.locator("#cityFilterList").count() == 1
    assert page.locator("#formatFilterList").count() == 1
    assert page.locator("#chainFilterList").count() == 1
    assert page.locator(".map-home-control-button").count() == 1

    # Layout remains sidebar -> list -> rightmost map. List width is intentionally unchanged.
    sidebar = page.locator(".sidebar").bounding_box()
    cinema_list = page.locator("#cinemaListPanel").bounding_box()
    map_wrap = page.locator(".map-wrap").bounding_box()
    assert sidebar and cinema_list and map_wrap
    assert sidebar["x"] < cinema_list["x"] < map_wrap["x"], (sidebar, cinema_list, map_wrap)
    assert 330 <= cinema_list["width"] <= 410, cinema_list
    assert map_wrap["x"] + map_wrap["width"] >= 1430, map_wrap

    # Header no longer repeats movie title/update copy.
    assert page.locator("#cinemaListPanel .movie-detail-seo-copy").count() == 0
    assert page.locator(".cinema-list-head h2").inner_text() == "影城列表"

    # Compact cards: name + showtimes only; fixed short height; no distance shown.
    first_card = page.locator("#cinemaList .cinema-list-card").first
    card_box = first_card.bounding_box()
    assert card_box and card_box["height"] <= 72, card_box
    assert first_card.locator(".cinema-list-name").count() == 1
    assert first_card.locator(".cinema-list-times").count() == 1
    assert first_card.locator("a, button, .popup-links, .cinema-list-distance").count() == 0
    assert "公里" not in first_card.inner_text()
    assert "公尺" not in first_card.inner_text()

    # Geolocation still silently orders the list nearest-first.
    page.wait_for_function(
        "() => [...document.querySelectorAll('#cinemaList .cinema-list-card')].some(c => c.dataset.distance)"
    )
    distances = page.locator("#cinemaList .cinema-list-card").evaluate_all(
        "cards => cards.map(c => Number(c.dataset.distance)).filter(Number.isFinite)"
    )
    assert distances == sorted(distances), distances

    # The list remains driven by original filters.
    initial_count = int(page.locator("#cinemaListCount").inner_text())
    assert initial_count > 0
    city_buttons = page.locator("#cityFilterList .filter-option")
    if city_buttons.count() > 1:
        target = city_buttons.nth(0)
        target.click()
        page.wait_for_timeout(100)
        filtered_count = int(page.locator("#cinemaListCount").inner_text())
        assert 1 <= filtered_count <= initial_count
        target.click()
        page.wait_for_timeout(100)

    # Original markers and popup remain the detail/action surface.
    assert page.locator(".cinema-marker").count() > 0
    page.locator(".leaflet-marker-icon").first.click(force=True)
    page.locator(".leaflet-popup:visible").last.wait_for(timeout=5000)
    assert page.locator(".cinema-list-card.is-active").count() == 1
    assert page.locator(".leaflet-popup:visible .popup-links").count() > 0

    # Clicking compact list delegates to original map focus / popup.
    first_card = page.locator("#cinemaList .cinema-list-card").first
    first_card.click()
    page.locator(".leaflet-popup:visible").last.wait_for(timeout=5000)

    # Movie change must navigate to that movie's canonical independent URL.
    target_info = page.evaluate(
        """() => {
          const links = window.MuseMoviePageLinks || {};
          const current = document.querySelector('#movieSelect')?.value || '';
          const target = Object.keys(links).find(name => name !== current);
          return target ? { target, href: links[target] } : null;
        }"""
    )
    if target_info:
        page.evaluate(
            """({target}) => {
              const select = document.querySelector('#movieSelect');
              if (![...select.options].some(option => option.value === target)) {
                select.add(new Option(target, target));
              }
              select.value = target;
              select.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"target": target_info["target"]},
        )
        page.wait_for_url(f"**/{target_info['href']}")
        assert page.url.endswith("/" + target_info["href"])


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

        assert page.locator("#cinemaListPanel").is_hidden()
        assert page.locator("#mSeg").is_visible()
        assert page.locator(".sidebar").is_visible()
        assert page.locator("#map").is_visible()
        assert page.locator("#mSheet").count() == 1

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
