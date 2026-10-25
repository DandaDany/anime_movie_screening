from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "web" / "data" / "movie_discovery.json"
ASSETS = ROOT / "web" / "assets" / "posters"
UPDATED_IDS = set(range(34, 43)) | {5, 25}
BASE_URL = "http://127.0.0.1:8765/"


def wait_img(image) -> dict:
    image.evaluate(
        """img => {
            if (img.complete && img.naturalWidth > 0) return true;
            return new Promise((resolve) => {
                const done = () => resolve(true);
                img.addEventListener('load', done, {once: true});
                img.addEventListener('error', done, {once: true});
                setTimeout(done, 20000);
            });
        }"""
    )
    return image.evaluate(
        """img => ({
            src: img.currentSrc || img.src || '',
            complete: img.complete,
            naturalWidth: img.naturalWidth || 0,
            naturalHeight: img.naturalHeight || 0,
            fallbackTried: img.dataset.posterFallbackTried || '',
            missing: img.closest('.movie-card__poster')?.classList.contains('is-missing') || false
        })"""
    )


def probe_image(page, url: str) -> dict:
    return page.evaluate(
        """async url => {
            const img = new Image();
            img.referrerPolicy = 'no-referrer';
            img.decoding = 'async';
            const outcome = await Promise.race([
                new Promise(resolve => {
                    img.onload = () => resolve('loaded');
                    img.onerror = () => resolve('error');
                    img.src = url;
                }),
                new Promise(resolve => setTimeout(() => resolve('timeout'), 20000))
            ]);
            return {
                outcome,
                src: img.currentSrc || img.src || url,
                complete: img.complete,
                naturalWidth: img.naturalWidth || 0,
                naturalHeight: img.naturalHeight || 0
            };
        }""",
        url,
    )


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert catalog["missing_poster_count"] == 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1200},
                timezone_id="Asia/Taipei",
                locale="zh-TW",
            )
            page = context.new_page()
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            page.locator("#comingSoonGrid .movie-card").first.wait_for(timeout=30000)
            upcoming_cards = page.locator("#comingSoonGrid .movie-card")
            print("[poster-runtime] upcoming_cards=", upcoming_cards.count(), flush=True)
            failures = []
            for index in range(upcoming_cards.count()):
                card = upcoming_cards.nth(index)
                title = card.get_attribute("data-movie-title") or card.inner_text()
                card.scroll_into_view_if_needed()
                state = wait_img(card.locator("img"))
                print("[poster-runtime] UPCOMING", title, json.dumps(state, ensure_ascii=False), flush=True)
                if not state["complete"] or state["naturalWidth"] <= 0 or state["naturalHeight"] <= 0 or state["missing"]:
                    failures.append({"title": title, **state})

            # Newly introduced posters and in-flight replacements must really
            # decode in Chromium, even if the current crawl has no showtimes
            # and a given released film does not appear in the now-showing grid.
            for movie in catalog["movies"]:
                if movie["id"] not in UPDATED_IDS:
                    continue
                state = probe_image(page, movie["poster_url"])
                w, h = state["naturalWidth"], state["naturalHeight"]
                print("[poster-runtime] NEW_OR_REPLACED", movie["title"], json.dumps(state, ensure_ascii=False), flush=True)
                if state["outcome"] != "loaded" or not state["complete"] or not w or not h:
                    failures.append({"title": movie["title"], **state})
                if w and h and (w < 800 or h < 1200):
                    print(
                        "[poster-runtime] LOW_RES_PENDING_UPGRADE",
                        movie["title"], str(w) + "x" + str(h),
                        flush=True,
                    )

            # Assert any rendered affected cards have no .is-missing state.
            for card in page.locator("#nowShowingGrid .movie-card").all():
                title = card.get_attribute("data-movie-title") or ""
                if title not in {m["title"] for m in catalog["movies"] if m["id"] in UPDATED_IDS}:
                    continue
                state = wait_img(card.locator("img"))
                print("[poster-runtime] CURRENT_CARD", title, json.dumps(state, ensure_ascii=False), flush=True)
                if not state["complete"] or state["naturalWidth"] <= 0 or state["naturalHeight"] <= 0 or state["missing"]:
                    failures.append({"title": title, **state})

            # Every local image must be decoded and dimension-checked; the old
            # Japanese Anpanman asset remains as an immutable regression sample.
            minimums = {
                "anpanman-pantan-2026-hq.webp": (1400, 2000),
                "kusuriya-movie-tw-20270129-hq.webp": (1400, 1950),
                "eupho-final-part1-tw.webp": (890, 1270),
            }
            for asset in sorted(ASSETS.iterdir()):
                if asset.suffix.lower() not in (".webp", ".jpg", ".jpeg", ".png"):
                    continue
                if asset.suffix.lower() == ".webp":
                    blob = asset.read_bytes()
                    assert len(blob) > 512, (asset.name, "too small")
                    assert blob[:4] == b"RIFF" and blob[8:12] == b"WEBP", asset.name
                    assert int.from_bytes(blob[4:8], "little") + 8 == len(blob), asset.name
                elif asset.suffix.lower() in (".jpg", ".jpeg"):
                    blob = asset.read_bytes()
                    assert blob.startswith(b"\xff\xd8\xff") and blob.endswith(b"\xff\xd9"), asset.name
                else:
                    assert asset.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"), asset.name
                state = probe_image(page, "assets/posters/" + asset.name)
                print("[poster-runtime] LOCAL", asset.name, json.dumps(state, ensure_ascii=False), flush=True)
                min_width, min_height = minimums.get(asset.name, (800, 1200))
                if not state["complete"] or state["outcome"] != "loaded" or state["naturalWidth"] < min_width or state["naturalHeight"] < min_height:
                    failures.append({"asset": asset.name, **state})

            # Verify actual app fallback logic, not merely the URL string.
            copy = json.loads(json.dumps(catalog))
            chosen = next(item for item in copy["movies"] if item["title"] == "劇場版 藥師少女的獨語 亡妃的秘寶")
            chosen["poster_url"] = "assets/posters/intentional-runtime-404.jpg"
            chosen["poster_fallback_url"] = "assets/posters/kusuriya-movie-tw-20270129-hq.webp"
            fallback_page = context.new_page()
            fallback_page.route(
                "**/data/movie_discovery.json",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(copy, ensure_ascii=False),
                ),
            )
            fallback_page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            fallback_page.wait_for_function("() => Boolean(window.MuseDiscovery)")
            test_card = fallback_page.locator(
                '#comingSoonGrid .movie-card[data-movie-title="劇場版 藥師少女的獨語 亡妃的秘寶"]'
            )
            test_card.wait_for(timeout=30000)
            test_card.scroll_into_view_if_needed()
            test_img = test_card.locator("img")
            test_img.evaluate(
                """img => new Promise(resolve => {
                    if (img.dataset.posterFallbackTried === '1' && img.complete && img.naturalWidth > 0) {
                        resolve(true); return;
                    }
                    const check = setInterval(() => {
                        if (img.dataset.posterFallbackTried === '1' && img.complete) {
                            clearInterval(check); resolve(true);
                        }
                    }, 50);
                    setTimeout(() => {clearInterval(check); resolve(false)}, 15000);
                })"""
            )
            fallback_state = wait_img(test_img)
            print("[poster-runtime] FALLBACK_BEHAVIOUR", json.dumps(fallback_state, ensure_ascii=False), flush=True)
            if (
                fallback_state["fallbackTried"] != "1"
                or not fallback_state["src"].endswith("/assets/posters/kusuriya-movie-tw-20270129-hq.webp")
                or not fallback_state["complete"]
                or fallback_state["naturalWidth"] <= 0
                or fallback_state["naturalHeight"] <= 0
                or fallback_state["missing"]
            ):
                failures.append({"test": "fallback_switch", **fallback_state})
            fallback_page.close()
            context.close()
            assert not failures, "poster runtime failures: " + json.dumps(failures, ensure_ascii=False)
            print("[poster-runtime] PASS: upcoming + new/replaced + local + browser fallback", flush=True)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
