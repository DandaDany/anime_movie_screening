from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"


def find_movie_with_showtimes() -> Path:
    for path in sorted(WEB.glob("movie-*.html")):
        if 'class="cinema-card"' in path.read_text(encoding="utf-8"):
            return path
    raise AssertionError("expected at least one generated movie page with showtimes")


def block_map_tiles(page) -> None:
    page.route("**/basemaps.cartocdn.com/**", lambda route: route.abort())


def visible_cards_with_coordinates(page) -> int:
    return page.locator(".cinema-card:visible").evaluate_all(
        """cards => cards.filter(card =>
            Number.isFinite(Number(card.dataset.lat)) &&
            Number.isFinite(Number(card.dataset.long)) &&
            card.dataset.lat !== '' &&
            card.dataset.long !== ''
        ).length"""
    )


def verify_desktop(page, movie_file: str) -> None:
    block_map_tiles(page)
    page.goto(f"http://127.0.0.1:8765/{movie_file}", wait_until="domcontentloaded")
    page.locator("#movieMap.leaflet-container").wait_for(timeout=30000)
    page.locator(".cinema-card").first.wait_for()

    assert page.locator(".site-brand").inner_text().strip() == "電影場次"
    assert page.locator("h1").inner_text().strip()
    assert page.locator(".map-cta").count() == 0
    assert page.locator("#movieSearch").count() == 1
    assert page.locator("#movieDateFilters").count() == 1
    assert page.locator("#movieCityFilters").count() == 1
    assert page.locator("#movieFormatFilters").count() == 1
    assert page.locator("#movieChainFilters").count() == 1
    assert page.locator("#moviePeriodFilters").count() == 1

    # Test against the complete selected-date inventory instead of depending on wall-clock time.
    now_toggle = page.locator("#movieNowToggle")
    if now_toggle.get_attribute("aria-pressed") == "true":
        now_toggle.click()

    page.wait_for_function(
        "() => Number(document.querySelector('#movieResultCount')?.textContent || 0) > 0"
    )
    page.locator("#distanceStatus").filter(has_text="已依你目前的位置").wait_for(timeout=15000)

    expected_markers = visible_cards_with_coordinates(page)
    page.wait_for_function(
        "(expected) => document.querySelectorAll('.leaflet-marker-icon').length >= expected",
        arg=expected_markers,
    )
    assert page.locator(".leaflet-marker-icon").count() >= expected_markers

    city_buttons = page.locator("[data-filter-city]:not([data-filter-city='']):visible")
    if city_buttons.count():
        button = city_buttons.first
        selected_city = button.get_attribute("data-filter-city")
        button.click()
        visible_cards = page.locator(".cinema-card:visible")
        assert visible_cards.count() > 0
        for index in range(visible_cards.count()):
            assert visible_cards.nth(index).get_attribute("data-city") == selected_city

        page.locator("[data-filter-city='']").click()

    format_buttons = page.locator("[data-filter-format]:not([data-filter-format='']):visible")
    if format_buttons.count():
        button = format_buttons.first
        selected_format = button.get_attribute("data-filter-format")
        button.click()
        visible_chips = page.locator(".showtime-chip:visible")
        assert visible_chips.count() > 0
        for index in range(visible_chips.count()):
            values = (visible_chips.nth(index).get_attribute("data-formats") or "").split("|")
            assert selected_format in values
        page.locator("[data-filter-format='']").click()

    chain_buttons = page.locator("[data-filter-chain]:not([data-filter-chain='']):visible")
    if chain_buttons.count():
        button = chain_buttons.first
        selected_chain = button.get_attribute("data-filter-chain")
        button.click()
        visible_cards = page.locator(".cinema-card:visible")
        assert visible_cards.count() > 0
        for index in range(visible_cards.count()):
            assert visible_cards.nth(index).get_attribute("data-chain") == selected_chain
        page.locator("[data-filter-chain='']").click()

    markers = page.locator(".leaflet-marker-icon")
    if markers.count():
        markers.first.click(force=True)
        page.locator(".cinema-card.is-map-active").wait_for()

    first_card = page.locator(".cinema-card:visible").first
    first_card.click(position={"x": 8, "y": 8})
    assert "is-map-active" in (first_card.get_attribute("class") or "")

    bookable = page.locator(".showtime-chip.is-bookable:visible")
    if bookable.count():
        chip = bookable.first
        expected = chip.get_attribute("data-booking-url")
        card = chip.locator("xpath=ancestor::article[contains(@class,'cinema-card')]")
        cta = card.locator("[data-booking-cta]")
        chip.click()
        assert cta.get_attribute("aria-disabled") == "false"
        assert cta.get_attribute("href") == expected

    assert page.locator(".cinema-action", has_text="官方網站").count() > 0


def verify_mobile(playwright, movie_file: str) -> None:
    context = playwright.chromium.launch(headless=True)
    try:
        mobile = context.new_context(
            viewport={"width": 390, "height": 844},
            timezone_id="Asia/Taipei",
            locale="zh-TW",
            geolocation={"latitude": 25.0330, "longitude": 121.5654},
            permissions=["geolocation"],
        )
        page = mobile.new_page()
        block_map_tiles(page)
        page.goto(f"http://127.0.0.1:8765/{movie_file}", wait_until="domcontentloaded")
        page.locator("#movieMap.leaflet-container").wait_for(timeout=30000)
        grabber = page.locator("#movieSheetGrabber")
        grabber.wait_for()
        assert grabber.is_visible()

        workspace = page.locator("#movieWorkspace")
        before = workspace.evaluate("el => el.getBoundingClientRect().height")
        box = grabber.bounding_box()
        assert box
        x = box["x"] + box["width"] / 2
        y = box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x, y - 120, steps=5)
        page.mouse.up()
        after = workspace.evaluate("el => el.getBoundingClientRect().height")
        assert after > before, (before, after)

        assert page.locator("#movieMap").evaluate("el => el.getBoundingClientRect().height") > 0
        mobile.close()
    finally:
        context.close()


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
