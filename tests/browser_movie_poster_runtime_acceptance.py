from __future__ import annotations

from playwright.sync_api import sync_playwright


def main() -> int:
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
                print(f"UPCOMING_POSTER {title}: {state['naturalWidth']}x{state['naturalHeight']} loaded={state['complete']} missing={state['missing']}")
                if state["naturalWidth"] < 800 or state["naturalHeight"] < 1200:
                    print(f"LOW_RES_PENDING_UPGRADE {title}: {state['naturalWidth']}x{state['naturalHeight']}")
                if (
                    not state["complete"]
                    or state["naturalWidth"] <= 0
                    or state["naturalHeight"] <= 0
                    or state["missing"]
                ):
                    failures.append({"title": title, **state})

            bangdream = page.locator(
                '.movie-card[data-movie-title="BanG Dream! Ave Mujica prima aurora"]'
            )
            bang_img = bangdream.locator("img")
            assert bang_img.evaluate("img => getComputedStyle(img).objectFit") == "contain"
            assert bang_img.evaluate("img => getComputedStyle(img).objectPosition") in ("50% 50%", "center")

            anpanman = page.locator(
                '.movie-card[data-movie-title="麵包超人電影版：潘坦與約定之星"]'
            )
            anpan_src = anpanman.locator("img").evaluate("img => img.currentSrc || img.src")
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
                print(f"LOCAL_POSTER {asset_path}: {state['width']}x{state['height']} decoded")

            # Force the primary Taiwan poster to fail and validate the real
            # fallback path in Chromium, rather than just checking a URL string.
            fallback_page = context.new_page()
            fallback_page.route(
                "**/images/63afc0f9c4a805a05f5c9e4449d8cda7.jpg",
                lambda route: route.abort(),
            )
            fallback_page.goto("http://127.0.0.1:8765/", wait_until="domcontentloaded", timeout=60000)
            fallback_page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            paw = fallback_page.locator(
                '.movie-card[data-movie-title="汪汪隊立大功：恐龍大電影"]'
            )
            paw.wait_for(timeout=30000)
            fallback_state = paw.locator("img").evaluate(
                """async img => {
                    for (let i = 0; i < 150 && (!img.complete || !img.dataset.posterFallbackTried); i++)
                        await new Promise(resolve => setTimeout(resolve, 100));
                    return {
                        src: img.currentSrc || img.src,
                        complete: img.complete,
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        attempted: img.dataset.posterFallbackTried || "",
                        missing: img.closest('.movie-card__poster')?.classList.contains('is-missing') || false
                    };
                }"""
            )
            assert fallback_state["attempted"] == "1", fallback_state
            assert fallback_state["src"].endswith("/ForVsWeb/upload/film/film_20260401001.jpg"), fallback_state
            assert fallback_state["complete"] and fallback_state["width"] > 0 and fallback_state["height"] > 0, fallback_state
            assert not fallback_state["missing"], fallback_state
            print(f"FALLBACK_POSTER 汪汪隊立大功：恐龍大電影: {fallback_state['width']}x{fallback_state['height']} decoded")
            fallback_page.close()

            assert not failures, f"poster runtime failures: {failures}"
            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
