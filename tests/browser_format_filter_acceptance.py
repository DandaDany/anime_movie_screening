from __future__ import annotations

import json
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "format_filter_locations.geojson"
FIXED_NOW_MS = 1786519200000  # 2026-08-12 15:20 Asia/Taipei


def install_fixture(page):
    body = FIXTURE.read_text(encoding="utf-8")
    page.route("**/data/locations.geojson", lambda route: route.fulfill(
        status=200, content_type="application/geo+json", body=body
    ))
    page.add_init_script(f"""
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
    """)


def enter_map(page):
    page.wait_for_function("() => Boolean(window.MuseDiscovery)")
    page.evaluate("window.MuseDiscovery.close()")
    page.wait_for_timeout(250)


def run_case(page, mobile: bool):
    page.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    enter_map(page)

    if mobile:
        page.locator("#mSeg button[data-tab='format']").click()

    format_buttons = page.locator("#formatFilterList .filter-option")
    labels = format_buttons.locator("span").all_text_contents()
    assert "IMAX" in labels
    assert "4DX" in labels
    assert "3D" in labels
    assert "Dolby" in labels
    assert "INFINITY VISION" in labels
    assert "數位" in labels

    page.locator("#formatFilterList .filter-option", has_text="IMAX").click()
    page.wait_for_timeout(100)
    assert page.locator(".cinema-marker").count() == 1
    assert page.locator(".cinema-showtime-count").all_text_contents() == ["1"]

    page.locator(".cinema-marker").first.dispatch_event("click")
    container = page.locator("#mSheetBody") if mobile else page.locator(".leaflet-popup").last
    container.wait_for()
    text = container.inner_text()
    assert "16:00" in text
    assert "19:00" not in text

    if mobile:
        page.locator("#mSheetClose").click()
        page.wait_for_timeout(100)
        page.locator("#mSeg button[data-tab='format']").click()
    page.locator("#formatFilterList .filter-option", has_text="IMAX").click()
    page.wait_for_timeout(100)
    assert page.locator(".cinema-marker").count() == 2

    page.locator("#formatFilterList .filter-option", has_text="4DX").click()
    page.wait_for_timeout(100)
    assert page.locator(".cinema-marker").count() == 1
    assert page.locator(".cinema-showtime-count").all_text_contents() == ["1"]


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
                install_fixture(page)
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
