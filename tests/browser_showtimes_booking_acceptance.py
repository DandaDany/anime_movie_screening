from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

FIXED_NOW_MS = 1790439300000  # 2026-09-27 00:15 Asia/Taipei
MOVIE_TITLE = "劇場版 吉伊卡哇 人魚島的秘密"

PROVIDERS = [
    {
        "chain": "威秀影城 / VIESHOW",
        "location": "台北信義威秀影城",
        "booking_url": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=211704",
    },
    {
        "chain": "MUVIE CINEMAS",
        "location": "MUVIE CINEMAS 台北松仁",
        "booking_url": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=21&txtSessionId=165981",
    },
    {
        "chain": "秀泰影城",
        "location": "大巨蛋秀泰影城",
        "booking_url": "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27",
    },
    {
        "chain": "美麗華影城",
        "location": "美麗華影城",
        "booking_url": "https://www.miramarcinemas.tw/Booking/TicketType?id=movie-id&session=437780",
    },
    {
        "chain": "台鋁影城",
        "location": "MLD台鋁影城",
        "booking_url": "https://mldcinema.com.tw/OnlinePurchase.php?computerid=264704",
    },
    {
        "chain": "百老匯影城",
        "location": "公館百老匯影城",
        "booking_url": "https://www.broadway-cineplex.com.tw/book.html?obj=Taipei&v25080101",
    },
    {
        "chain": "中影屏東影城",
        "location": "中影屏東影城",
        "booking_url": "https://www.ezding.com.tw/cinemabooking?cinemaid=2c28121ae2c711e292f7000bdb90dba4",
    },
]

GENERAL_PROVIDER = {
    "chain": "喜樂時代影城",
    "location": "喜樂時代影城永和店",
    "booking_url": "https://ticket.centuryasia.com.tw/beyond/buyticket_process.aspx?ProgramID=0000154&eventsn=91&computerid=518213",
    "seat_preview_url": "https://ticket.centuryasia.com.tw/beyond/buyticket_process.aspx?ProgramID=0000154&eventsn=91&computerid=518213",
}


def locations_payload(provider: dict[str, str], location_id: int) -> dict:
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [121.561, 25.041]},
        "properties": {
            "location_id": location_id,
            "chain_name": provider["chain"],
            "location_name": provider["location"],
            "map_name": provider["location"],
            "address": "臺北市測試地址",
            "city": "臺北市",
            "location_url": "https://example.test/showtimes",
            "official_url": "https://example.test/official",
            "movie_title": MOVIE_TITLE,
            "show_date": "2026-09-27",
            "showtime_count": 1,
            "showtimes": [
                {
                    "time": "10:10",
                    "format": "數位",
                    "language": "日語",
                    "auditorium": "1廳",
                    "booking_url": provider["booking_url"],
                    "seat_preview_url": provider.get("seat_preview_url", ""),
                    "label": "10:10 數位 / 1廳",
                }
            ],
            "start_times": "10:10",
        },
    }
    return {
        "type": "FeatureCollection",
        "name": f'{provider["chain"]} booking acceptance',
        "show_date": "2026-09-27",
        "updated_at": "2026-09-27T00:10:00+08:00",
        "available_dates": ["2026-09-27"],
        "movies": [
            {
                "title": MOVIE_TITLE,
                "show_date": "2026-09-27",
                "available_dates": ["2026-09-27"],
                "feature_count": 1,
            }
        ],
        "movie_features": {MOVIE_TITLE: [feature]},
        "movie_features_by_date": {MOVIE_TITLE: {"2026-09-27": [feature]}},
        "features": [feature],
    }


def install_fixed_clock(page) -> None:
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


def assert_provider(browser, provider: dict[str, str], index: int) -> None:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        timezone_id="Asia/Taipei",
    )
    try:
        page = context.new_page()
        payload = locations_payload(provider, 990 + index)
        page.route(
            "**/data/locations.geojson",
            lambda route: route.fulfill(
                status=200,
                content_type="application/geo+json",
                body=json.dumps(payload, ensure_ascii=False),
            ),
        )
        install_fixed_clock(page)
        page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.MuseDiscovery)")
        page.evaluate("window.MuseDiscovery.close()")
        page.wait_for_timeout(250)

        marker = page.locator(".cinema-marker")
        assert marker.count() == 1, provider["chain"]
        marker.dispatch_event("click")

        popup = page.locator(".leaflet-popup").last
        popup.wait_for()
        cta = popup.locator("[data-booking-cta]")
        assert cta.count() == 1, f'{provider["chain"]}: missing dynamic booking CTA'
        assert cta.inner_text() == "前往訂票", provider["chain"]
        assert cta.get_attribute("aria-disabled") == "true", provider["chain"]
        assert not cta.get_attribute("href"), provider["chain"]

        showtime = popup.locator(".st-chip-select", has_text="10:10")
        assert showtime.count() == 1, f'{provider["chain"]}: showtime must be selectable'
        assert showtime.get_attribute("aria-pressed") == "false", provider["chain"]
        showtime.dispatch_event("click")

        assert showtime.get_attribute("aria-pressed") == "true", provider["chain"]
        assert cta.inner_text() == "前往訂票", provider["chain"]
        assert cta.get_attribute("href") == provider["booking_url"], provider["chain"]
        assert cta.get_attribute("aria-disabled") == "false", provider["chain"]
    finally:
        context.close()


def assert_general_provider(browser) -> None:
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        timezone_id="Asia/Taipei",
    )
    try:
        page = context.new_page()
        payload = locations_payload(GENERAL_PROVIDER, 999)
        page.route(
            "**/data/locations.geojson",
            lambda route: route.fulfill(
                status=200,
                content_type="application/geo+json",
                body=json.dumps(payload, ensure_ascii=False),
            ),
        )
        install_fixed_clock(page)
        page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        page.wait_for_function("() => Boolean(window.MuseDiscovery)")
        page.evaluate("window.MuseDiscovery.close()")
        page.wait_for_timeout(250)

        marker = page.locator(".cinema-marker")
        assert marker.count() == 1
        marker.dispatch_event("click")

        popup = page.locator(".leaflet-popup").last
        popup.wait_for()
        assert popup.locator("[data-booking-cta]").count() == 0
        primary = popup.locator(".popup-link-primary")
        assert primary.count() == 1
        assert primary.inner_text() == "場次入口"
        assert primary.get_attribute("href") == "https://example.test/showtimes"
        assert popup.locator("[data-booking-cta]").count() == 0

        showtime = popup.locator(".st-chip-select", has_text="10:10")
        assert showtime.count() == 1
        assert showtime.get_attribute("aria-pressed") == "false"

        official = popup.locator("[data-official-cta]")
        assert official.inner_text() == "官方網站"
        showtime.dispatch_event("click")
        assert showtime.get_attribute("aria-pressed") == "true"
        assert official.inner_text() == "座位表入口"
        assert official.get_attribute("href") == GENERAL_PROVIDER["seat_preview_url"]
    finally:
        context.close()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for index, provider in enumerate(PROVIDERS, start=1):
                assert_provider(browser, provider, index)
            assert_general_provider(browser)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
