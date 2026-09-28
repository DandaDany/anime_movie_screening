from __future__ import annotations

from playwright.sync_api import sync_playwright


DIRECT_IMAGES = [
    ("bangdream_current", "https://www.major-j.com/upload/ticket/M09321725042/main.jpg"),
    ("madeinabyss_current", "https://www.major-j.com/upload/ticket/M20311755910/main.jpg"),
    ("fma_current", "https://www.sonymusic.co.jp/lineup/anime/hagaren-movie/img/keyv_l.jpg"),
    ("accelworld_current", "https://img.sunrise-inc.co.jp/images/datacard/377_main.jpg"),
    ("aobuta_current", "https://www.major-j.com/upload/ticket/M07318877037/main.jpg"),
    ("sumikko_current", "https://www.unicornpopcorn.com.tw/ForVsWeb/upload/film/film_20260714001.jpg"),
    ("anpanman_current", "https://news.anpan-movie.com/wp-content/uploads/2026/02/%E3%80%90RGB%E3%80%91%E6%9C%AC%E3%83%9D%E3%82%B9%E3%82%BF%E3%83%BC.jpg"),
    ("jinroh_current", "https://portal.cinemasunshine.smart-spoke.com/uploads/JIN_ROH_4_K_dd01facd15.jpg"),
    ("conan_current", "https://i.mopix.cc/GdRWN6.jpg"),
    ("fma_tw_candidate", "https://cdn12.nantoutheater.com/storages/movies/6ab0035c31090.jpg"),
    ("jinroh_tw_candidate", "https://media.nownews.com/nn_media/thumbnail/2026/09/1789974109673-410bc92058af4bfc926e40c6797b3dd5-800x1204.webp?unShow=false&waterMark=false"),
]

SOURCES = [
    ("fma_tw_vieshow", "https://www.vscinemas.com.tw/film/detail.aspx?id=8976"),
    ("fma_tw_nantou", "https://nantoutheater.com/movie/688"),
    ("fma_tw_gamme", "https://movie.gamme.com.tw/84998"),
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
        page.goto("about:blank")
        for label, image_url in DIRECT_IMAGES:
            result = page.evaluate(
                """async ({label, url}) => {
                    const img = new Image();
                    img.referrerPolicy = 'no-referrer';
                    const outcome = await new Promise((resolve) => {
                        const timer = setTimeout(() => resolve({ok:false, reason:'timeout'}), 20000);
                        img.onload = () => { clearTimeout(timer); resolve({ok:true}); };
                        img.onerror = () => { clearTimeout(timer); resolve({ok:false, reason:'error'}); };
                        img.src = url;
                    });
                    return {
                        label,
                        url,
                        ok: outcome.ok,
                        reason: outcome.reason || '',
                        width: img.naturalWidth || 0,
                        height: img.naturalHeight || 0
                    };
                }""",
                {"label": label, "url": image_url},
            )
            ratio = (result["width"] / result["height"]) if result["height"] else 0
            print(
                f"DIRECT {label} ok={result['ok']} reason={result['reason']} "
                f"{result['width']}x{result['height']} ratio={ratio:.3f} url={result['url']}"
            )

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
