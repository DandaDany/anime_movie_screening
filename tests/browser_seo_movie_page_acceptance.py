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

    # Original popup remains the detail/action surface.
    assert page.locator(".cinema-marker").count() > 0

    # First focus through the compact list so its marker is guaranteed to be in viewport.
    first_card = page.locator("#cinemaList .cinema-list-card").first
    first_card.click()
    page.locator(".leaflet-popup:visible").last.wait_for(timeout=5000)
    assert page.locator(".leaflet-popup:visible .popup-links").count() > 0

    # Then click an actually in-viewport marker and verify the list follows it.
    marker_center = page.evaluate(
        """() => {
          const marker = [...document.querySelectorAll('.leaflet-marker-icon')].find((el) => {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 &&
              rect.left >= 0 && rect.right <= innerWidth &&
              rect.top >= 0 && rect.bottom <= innerHeight;
          });
          if (!marker) return null;
          const rect = marker.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        }"""
    )
    assert marker_center, "expected an in-viewport original marker"
    page.mouse.click(marker_center["x"], marker_center["y"])
    page.locator(".leaflet-popup:visible").last.wait_for(timeout=5000)
    assert page.locator(".cinema-list-card.is-active").count() == 1

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
        page.locator("#cinemaList .cinema-list-card").first.wait_for(timeout=30000)

        # The compact cinema results become a Google-Maps-style horizontal carousel
        # immediately above the unchanged 40dvh filter tray.
        carousel = page.locator("#cinemaListPanel")
        assert carousel.is_visible()
        assert page.locator(".cinema-list-head").is_hidden()

        carousel_box = carousel.bounding_box()
        sidebar_box = page.locator(".sidebar").bounding_box()
        assert carousel_box and sidebar_box
        assert carousel_box["y"] + carousel_box["height"] <= sidebar_box["y"] + 4, (
            carousel_box,
            sidebar_box,
        )

        first_card = page.locator("#cinemaList .cinema-list-card").first
        card_box = first_card.bounding_box()
        assert card_box and card_box["height"] <= 72, card_box

        if page.locator("#cinemaList .cinema-list-card").count() > 1:
            overflow = page.locator("#cinemaList").evaluate(
                "el => ({scrollWidth: el.scrollWidth, clientWidth: el.clientWidth})"
            )
            assert overflow["scrollWidth"] > overflow["clientWidth"], overflow

        # Fixed chrome is compressed so the middle tab content gets materially more height.
        assert page.locator(".panel-head").is_hidden()
        assert page.locator(".sidebar-note").is_hidden()

        date_chips = page.locator(".date-chip:visible")
        if date_chips.count():
            date_box = date_chips.first.bounding_box()
            assert date_box and date_box["height"] <= 30, date_box

        tab_box = page.locator("#mSeg button").first.bounding_box()
        assert tab_box and tab_box["height"] <= 34, tab_box

        movie_panel = page.locator("#mMoviePanel")
        assert movie_panel.is_visible()
        movie_panel_box = movie_panel.bounding_box()
        assert movie_panel_box and movie_panel_box["height"] >= 170, movie_panel_box

        # City tab should also inherit the larger scrollable center area.
        page.locator("#mSeg button[data-tab='city']").click()
        city_block = page.locator("#cityBlock")
        city_block.wait_for()
        city_box = city_block.bounding_box()
        assert city_box and city_box["height"] >= 170, city_box

        # Tapping a carousel result delegates to the original mobile detail sheet.
        first_card.click()
        page.wait_for_function(
            "() => document.querySelector('.app-shell')?.classList.contains('sheet-open')"
        )
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"
        assert page.locator("#cinemaListPanel").evaluate(
            "el => getComputedStyle(el).opacity"
        ) == "0"

        # Close and verify the original marker interaction still works.
        page.locator("#mSheetClose").click()
        page.wait_for_function(
            "() => !document.querySelector('.app-shell')?.classList.contains('sheet-open')"
        )
        marker_center = page.evaluate(
            """() => {
              const marker = [...document.querySelectorAll('.leaflet-marker-icon')].find((el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 &&
                  rect.left >= 0 && rect.right <= innerWidth &&
                  rect.top >= 0 && rect.bottom <= innerHeight;
              });
              if (!marker) return null;
              const rect = marker.getBoundingClientRect();
              return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
            }"""
        )
        assert marker_center, "expected an in-viewport mobile marker"
        page.mouse.click(marker_center["x"], marker_center["y"])
        page.wait_for_function(
            "() => document.querySelector('.app-shell')?.classList.contains('sheet-open')"
        )
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"

        # Independent movie pages do not contain the discovery overlay themselves:
        # Home must navigate to the real homepage where mobile discovery lives.
        page.locator("#mSheetClose").click()
        page.wait_for_function(
            "() => !document.querySelector('.app-shell')?.classList.contains('sheet-open')"
        )
        home = page.locator(".map-home-control-button")
        assert home.get_attribute("href") == "./"
        home.click()
        page.wait_for_url("http://127.0.0.1:8765/")
        page.locator("#movieDiscovery").wait_for()
        assert page.locator("#movieDiscovery").is_visible()
        assert page.locator("#nowShowingTitle").inner_text() == "正在上映"
        assert page.locator("#comingSoonTitle").inner_text() == "即將上映"
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
