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


def close_info_surface(page, mobile: bool):
    if mobile:
        if page.locator("#mSheet").get_attribute("aria-hidden") == "false":
            page.locator("#mSheetClose").click()
            page.wait_for_timeout(120)
    else:
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)


def assert_single_result_auto_focus(
    page,
    mobile: bool,
    expected_times: list[str],
    excluded_times: list[str],
    before_marker_box=None,
):
    page.wait_for_timeout(650)
    assert page.locator(".cinema-marker").count() == 1

    if mobile:
        assert page.locator("#mSheet").get_attribute("aria-hidden") == "false"
        assert page.locator(".cinema-marker.is-mobile-selected").count() == 1
        container = page.locator("#mSheetBody")
        marker = page.locator(".cinema-marker.is-mobile-selected")
    else:
        container = page.locator(".leaflet-popup").last
        container.wait_for()
        marker = page.locator(".cinema-marker").first

    # focusFeature/openMobileSheet must move the map, not merely open UI over
    # the old viewport. Compare the same venue's on-screen position before and
    # after selecting the single-venue filter. We intentionally do not assert
    # an exact pixel center because desktop popup geometry and mobile safe-area
    # offsets differ by viewport/browser.
    if before_marker_box is not None:
        after_marker_box = marker.bounding_box()
        assert after_marker_box is not None
        before_x = before_marker_box["x"] + before_marker_box["width"] / 2
        before_y = before_marker_box["y"] + before_marker_box["height"] / 2
        after_x = after_marker_box["x"] + after_marker_box["width"] / 2
        after_y = after_marker_box["y"] + after_marker_box["height"] / 2
        displacement = ((after_x - before_x) ** 2 + (after_y - before_y) ** 2) ** 0.5
        assert displacement > 25, {
            "before": before_marker_box,
            "after": after_marker_box,
            "displacement": displacement,
        }

    text = container.inner_text()
    for expected in expected_times:
        assert expected in text
    for excluded in excluded_times:
        assert excluded not in text


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

    # Important: IMAX has TWO sessions but only ONE venue. Auto-focus must be
    # based on remaining venue count, not the numeric showtime count on the button.
    imax = page.locator("#formatFilterList .filter-option", has_text="IMAX")
    assert imax.locator("strong").inner_text() == "2"
    before_imax_box = page.locator(".cinema-marker[aria-label^='威秀影城']").bounding_box()
    assert before_imax_box is not None
    imax.click()
    assert page.locator(".cinema-showtime-count").all_text_contents() == ["2"]
    assert_single_result_auto_focus(
        page,
        mobile,
        expected_times=["16:00", "17:00"],
        excluded_times=["19:00"],
        before_marker_box=before_imax_box,
    )

    close_info_surface(page, mobile)
    if mobile:
        page.locator("#mSeg button[data-tab='format']").click()

    # Toggle IMAX off: both venues return and no auto-focus is requested.
    page.locator("#formatFilterList .filter-option", has_text="IMAX").click()
    page.wait_for_timeout(180)
    assert page.locator(".cinema-marker").count() == 2

    # A different version that leaves one venue must also auto-move/open.
    page.locator("#formatFilterList .filter-option", has_text="4DX").click()
    assert page.locator(".cinema-showtime-count").all_text_contents() == ["1"]
    assert_single_result_auto_focus(
        page,
        mobile,
        expected_times=["18:00"],
        excluded_times=["21:00"],
    )


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
    args = report
    print(json.dumps(args, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
