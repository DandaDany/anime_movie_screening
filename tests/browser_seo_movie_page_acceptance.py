from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"


def find_movie_with_showtimes() -> Path:
    for path in sorted(WEB.glob("movie-*.html")):
        if 'class="cinema-card"' in path.read_text(encoding="utf-8"):
            return path
    raise AssertionError("expected at least one generated movie page with showtimes")


def main() -> int:
    target = find_movie_with_showtimes()
    movie_file = target.name

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 1000},
                timezone_id="Asia/Taipei",
                locale="zh-TW",
                geolocation={"latitude": 25.0330, "longitude": 121.5654},
                permissions=["geolocation"],
            )
            page = context.new_page()
            page.goto(f"http://127.0.0.1:8765/{movie_file}", wait_until="networkidle")

            title = page.locator("h1").inner_text().strip()
            map_href = page.locator(".map-cta").get_attribute("href") or ""
            parsed_map_href = urlparse(map_href)
            query = parse_qs(parsed_map_href.query)
            assert parsed_map_href.path == "index.html", map_href
            assert query.get("restore") == ["1"], query
            assert query.get("movie"), query
            assert query.get("date"), query
            map_movie = query["movie"][0]

            update_text = page.locator(".movie-hero").inner_text()
            assert re.search(r"場次資料更新：(今日|\d{4}/\d{2}/\d{2}) \d{2}:\d{2}", update_text), update_text
            assert "+08:00" not in update_text
            assert "全台動畫電影場次" not in update_text

            assert page.locator("#movieFilterCity").count() == 1
            assert page.locator("#movieFilterFormat").count() == 1
            assert page.locator("#movieFilterTime").count() == 1

            page.locator("#distanceStatus").filter(has_text="已依你目前的位置").wait_for()
            for cinema_list in page.locator(".cinema-list").all():
                distances = cinema_list.locator(".cinema-card").evaluate_all(
                    "cards => cards.map(card => Number(card.dataset.distance)).filter(Number.isFinite)"
                )
                assert distances == sorted(distances), distances

            city_options = page.locator("#movieFilterCity option").evaluate_all(
                "opts => opts.map(o => o.value).filter(Boolean)"
            )
            if city_options:
                selected_city = city_options[0]
                page.locator("#movieFilterCity").select_option(selected_city)
                visible_cards = page.locator(".cinema-card:visible")
                assert visible_cards.count() > 0
                for index in range(visible_cards.count()):
                    assert visible_cards.nth(index).get_attribute("data-city") == selected_city
                page.locator("#movieFilterCity").select_option("")

            format_options = page.locator("#movieFilterFormat option").evaluate_all(
                "opts => opts.map(o => o.value).filter(Boolean)"
            )
            if format_options:
                selected_format = format_options[0]
                page.locator("#movieFilterFormat").select_option(selected_format)
                visible_cards = page.locator(".cinema-card:visible")
                assert visible_cards.count() > 0
                for index in range(visible_cards.count()):
                    visible_chips = visible_cards.nth(index).locator(".showtime-chip:visible")
                    assert visible_chips.count() > 0
                    assert any(
                        selected_format in (visible_chips.nth(chip_index).get_attribute("data-formats") or "").split("|")
                        for chip_index in range(visible_chips.count())
                    )
                page.locator("#movieFilterFormat").select_option("")

            first_chip = page.locator(".showtime-chip").first
            minute = int(first_chip.get_attribute("data-minute") or "0")
            if minute < 720:
                period = "morning"
                predicate = lambda value: value < 720
            elif minute < 1080:
                period = "afternoon"
                predicate = lambda value: 720 <= value < 1080
            else:
                period = "evening"
                predicate = lambda value: value >= 1080
            page.locator("#movieFilterTime").select_option(period)
            visible_chips = page.locator(".showtime-chip:visible")
            assert visible_chips.count() > 0
            for index in range(visible_chips.count()):
                value = int(visible_chips.nth(index).get_attribute("data-minute") or "0")
                assert predicate(value), (period, value)
            page.locator("#movieFilterTime").select_option("all")

            bookable = page.locator(".showtime-chip.is-bookable")
            if bookable.count():
                chip = bookable.first
                expected = chip.get_attribute("data-booking-url")
                card = chip.locator("xpath=ancestor::article[contains(@class,'cinema-card')]")
                cta = card.locator("[data-booking-cta]")
                chip.click()
                assert cta.get_attribute("aria-disabled") == "false"
                assert unquote(cta.get_attribute("href") or "") == unquote(expected or "")

            assert page.locator(".cinema-action", has_text="官方網站").count() > 0

            # The CTA must leave the detail page and restore the same map movie.
            page.locator(".map-cta").click()
            page.wait_for_url("**/index.html?**")
            page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            page.wait_for_function(
                "(movie) => document.querySelector('#movieSelect')?.value === movie",
                arg=map_movie,
            )
            assert page.locator("#movieSelect").input_value() == map_movie
            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
