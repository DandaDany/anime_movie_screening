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
                if (
                    not state["complete"]
                    or state["naturalWidth"] <= 0
                    or state["naturalHeight"] <= 0
                    or state["missing"]
                ):
                    failures.append({"title": title, **state})

            bangdream = page.locator(
                '#comingSoonGrid .movie-card[data-movie-title="BanG Dream! Ave Mujica prima aurora"]'
            )
            bang_img = bangdream.locator("img")
            assert bang_img.evaluate("img => getComputedStyle(img).objectFit") == "contain"

            anpanman = page.locator(
                '#comingSoonGrid .movie-card[data-movie-title="麵包超人電影版：潘坦與約定之星"]'
            )
            anpan_src = anpanman.locator("img").evaluate("img => img.currentSrc || img.src")
            assert anpan_src.endswith("/assets/posters/anpanman-pantan-2026.webp"), anpan_src

            kusuriya = page.locator(
                '#comingSoonGrid .movie-card[data-movie-title="劇場版 藥師少女的獨語 亡妃的秘寶"]'
            )
            assert kusuriya.count() == 1
            kusuriya_img = kusuriya.locator("img")
            kusuriya_src = kusuriya_img.evaluate("img => img.currentSrc || img.src")
            assert kusuriya_src.endswith("/assets/posters/kusuriya-movie-tw-20270129.webp"), kusuriya_src
            assert kusuriya_img.evaluate("img => getComputedStyle(img).objectFit") == "contain"

            assert not failures, f"poster runtime failures: {failures}"
            context.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
