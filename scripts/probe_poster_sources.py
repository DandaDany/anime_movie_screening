from __future__ import annotations

from playwright.sync_api import sync_playwright

SOURCES = [
    ("fma_tw_vieshow", "https://www.vscinemas.com.tw/film/detail.aspx?id=8976"),\n    ("fma_tw_nantou", "https://nantoutheater.com/movie/688"),\n    ("fma_tw_gamme", "https://movie.gamme.com.tw/84998"),
    ("jinroh_tw_nownews", "https://www.nownews.com/news/6876853"),
    ("jinroh_tw_gnn", "https://gnn.gamer.com.tw/detail.php?sn=311969"),
]


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1600},
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        for label, page_url in SOURCES:
            try:
                response = page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
                print(
                    f"PAGE {label} status={response.status if response else 'none'} "
                    f"url={page.url} title={page.title()!r}"
                )
                page.wait_for_timeout(3000)
                images = page.locator("img").evaluate_all(
                    """els => els.map((img) => ({
                        src: img.currentSrc || img.src || '',
                        alt: img.alt || '',
                        width: img.naturalWidth || 0,
                        height: img.naturalHeight || 0,
                        renderedWidth: img.getBoundingClientRect().width || 0,
                        renderedHeight: img.getBoundingClientRect().height || 0
                    })).filter(x => x.src && x.width > 0 && x.height > 0)"""
                )
                ranked = sorted(
                    images,
                    key=lambda x: (
                        abs((x["width"] / x["height"]) - (2 / 3)),
                        -(x["width"] * x["height"]),
                    ),
                )
                for item in ranked[:30]:
                    ratio = item["width"] / item["height"]
                    print(
                        f"IMG {label} {item['width']}x{item['height']} ratio={ratio:.3f} "
                        f"rendered={item['renderedWidth']:.0f}x{item['renderedHeight']:.0f} "
                        f"alt={item['alt']!r} url={item['src']}"
                    )
            except Exception as exc:
                print(f"ERROR {label}: {type(exc).__name__}: {exc}")
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
