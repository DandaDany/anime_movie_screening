from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "web" / "data" / "movie_discovery.json"


def main() -> int:
    catalog = json.loads(FEED.read_text(encoding="utf-8"))
    poster_sources = {item["title"]: str(item.get("poster_source") or "") for item in catalog["movies"]}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                timezone_id="Asia/Taipei",
                locale="zh-TW",
            )
            page = context.new_page()
            page.goto("http://127.0.0.1:8765/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            page.locator("#comingSoonGrid .movie-card").first.wait_for(timeout=30000)

            cards = page.locator("#comingSoonGrid .movie-card")
            count = cards.count()
            assert count > 0, "expected at least one upcoming movie card"

            failures = []
            for index in range(count):
                card = cards.nth(index)
                title = card.get_attribute("data-movie-title") or card.inner_text()
                card.scroll_into_view_if_needed()
                img = card.locator("img")
                img.evaluate(
                    """img => {
                        if (img.complete) return true;
                        return new Promise((resolve) => {
                            const done = () => resolve(true);
                            img.addEventListener('load', done, { once: true });
                            img.addEventListener('error', done, { once: true });
                            setTimeout(done, 15000);
                        });
                    }"""
                )
                state = img.evaluate(
                    """img => ({
                        src: img.currentSrc || img.src || '',
                        complete: img.complete,
                        naturalWidth: img.naturalWidth || 0,
                        naturalHeight: img.naturalHeight || 0,
                        fallbackTried: img.dataset.posterFallbackTried || '',
                        missing: img.closest('.movie-card__poster')?.classList.contains('is-missing') || false
                    })"""
                )
                if (
                    not state["complete"]
                    or state["naturalWidth"] <= 0
                    or state["naturalHeight"] <= 0
                    or state["missing"]
                ):
                    failures.append({"title": title, **state})
                is_low_res = state["naturalWidth"] < 800 or state["naturalHeight"] < 1200
                low_res_flag = "LOW_RES_PENDING_UPGRADE" in poster_sources.get(title, "")
                print(
                    f"[poster runtime] {title}: "
                    f"{state['naturalWidth']}x{state['naturalHeight']} "
                    f"loaded={state['complete'] and not state['missing']} "
                    f"low_res={is_low_res} LOW_RES_PENDING_UPGRADE={low_res_flag}",
                    flush=True,
                )
                if is_low_res and not low_res_flag:
                    print(f"[poster quality] EXISTING_LOW_RES_PENDING_REVIEW: {title}", flush=True)

            assert not failures, f"poster runtime failures: {failures}"

            # Film releases pass, and cards can move out of the upcoming shelf or
            # disappear from today's shelf if no bookable session exists. The
            # image regression remains mandatory when that card is rendered;
            # the local poster binary is tested independently below.
            bangdream = page.locator(
                '.movie-card[data-movie-title="BanG Dream! Ave Mujica prima aurora"]'
            )
            if bangdream.count():
                bang_img = bangdream.first.locator("img")
                assert bang_img.evaluate("img => getComputedStyle(img).objectFit") == "contain"
                assert bang_img.evaluate("img => getComputedStyle(img).objectPosition") in ("50% 50%", "center")

            anpanman = page.locator(
                '.movie-card[data-movie-title="麵包超人電影版：潘坦與約定之星"]'
            )
            if anpanman.count():
                anpan_src = anpanman.first.locator("img").evaluate("img => img.currentSrc || img.src")
                assert anpan_src.endswith("/assets/posters/anpanman-pantan-2026-hq.webp"), anpan_src

            kusuriya = page.locator(
                '#comingSoonGrid .movie-card[data-movie-title="劇場版 藥師少女的獨語 亡妃的秘寶"]'
            )
            assert kusuriya.count() == 1
            kusuriya_img = kusuriya.locator("img")
            kusuriya_src = kusuriya_img.evaluate("img => img.currentSrc || img.src")
            assert kusuriya_src.endswith("/assets/posters/kusuriya-movie-tw-20270129-hq.webp"), kusuriya_src
            assert kusuriya_img.evaluate("img => getComputedStyle(img).objectFit") == "contain"
            assert kusuriya_img.evaluate("img => getComputedStyle(img).objectPosition") in ("50% 50%", "center")

            required_local_assets = [
                ("assets/posters/anpanman-pantan-2026-hq.webp", 1400, 2000),
                ("assets/posters/kusuriya-movie-tw-20270129-hq.webp", 1400, 1950),
                ("assets/posters/eupho-final-part1-tw.webp", 890, 1270),
            ]
            for asset_path, min_width, min_height in required_local_assets:
                state = page.evaluate(
                    """async ([src, minWidth, minHeight]) => {
                        const img = new Image();
                        const done = new Promise((resolve) => {
                            img.onload = () => resolve({
                                complete: img.complete,
                                width: img.naturalWidth,
                                height: img.naturalHeight,
                                src: img.currentSrc || img.src
                            });
                            img.onerror = () => resolve({
                                complete: img.complete,
                                width: img.naturalWidth,
                                height: img.naturalHeight,
                                src: img.currentSrc || img.src
                            });
                        });
                        img.src = src;
                        document.body.appendChild(img);
                        const result = await done;
                        img.remove();
                        return {...result, minWidth, minHeight};
                    }""",
                    [asset_path, min_width, min_height],
                )
                assert state["complete"], state
                assert state["width"] >= min_width, state
                assert state["height"] >= min_height, state

            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
