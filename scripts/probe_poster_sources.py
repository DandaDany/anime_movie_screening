from __future__ import annotations

import io
import json
from pathlib import Path

import requests
from PIL import Image

POSTERS = {
    "bangdream.webp": {
        "url": "https://avemujica-movie.bang-dream.com/wordpress/wp-content/themes/avemujica-movie/assets/webp/common/index/img_kv_01.webp",
        "expected_min": (800, 1200),
    },
    "made-in-abyss.jpg": {
        "url": "https://miabyss.com/part1_images/news/p_015.jpg",
        "expected_min": (1000, 1500),
    },
    "fma-milos.jpg": {
        "url": "https://cdn12.nantoutheater.com/storages/movies/6ab0035c31090.jpg",
        "expected_min": (700, 1000),
    },
    "accel-world.jpg": {
        "url": "https://img.sunrise-inc.co.jp/images/datacard/377_main.jpg",
        "expected_min": (400, 500),
    },
    "aobuta.jpg": {
        "url": "https://ao-buta.com/assets/img/kv_dearfriend.jpg",
        "expected_min": (1000, 1500),
    },
    "sumikko.jpg": {
        "url": "https://www.unicornpopcorn.com.tw/ForVsWeb/upload/film/film_20260714001.jpg",
        "expected_min": (300, 450),
    },
    "anpanman.jpg": {
        "url": "https://news.anpan-movie.com/wp-content/uploads/2026/02/%E3%80%90RGB%E3%80%91%E6%9C%AC%E3%83%9D%E3%82%B9%E3%82%BF%E3%83%BC.jpg",
        "expected_min": (800, 1100),
    },
    "jinroh.webp": {
        "url": "https://media.nownews.com/nn_media/thumbnail/2026/09/1789974109673-410bc92058af4bfc926e40c6797b3dd5-800x1204.webp?unShow=false&waterMark=false",
        "expected_min": (700, 1000),
    },
    "conan30.jpg": {
        "url": "https://www.ccpa.org.tw/ccpa/images/ckfinder/2/images/01_%20%E4%B8%BB%E8%A6%96%E8%A6%BA%E6%B5%B7%E5%A0%B1.jpg",
        "expected_min": (700, 1000),
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
}

def main() -> int:
    out = Path("artifacts/posters")
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    session = requests.Session()

    for filename, cfg in POSTERS.items():
        url = cfg["url"]
        r = session.get(url, headers=HEADERS, timeout=40)
        print(f"GET {filename} status={r.status_code} ctype={r.headers.get('content-type')} bytes={len(r.content)}")
        r.raise_for_status()
        image = Image.open(io.BytesIO(r.content))
        width, height = image.size
        ratio = width / height
        min_w, min_h = cfg["expected_min"]
        if width < min_w or height < min_h:
            raise RuntimeError(f"{filename}: too small {width}x{height}")
        if not 0.55 <= ratio <= 0.82:
            raise RuntimeError(f"{filename}: not poster-like ratio {ratio:.3f}")
        (out / filename).write_bytes(r.content)
        manifest[filename] = {
            "width": width,
            "height": height,
            "ratio": round(ratio, 4),
            "source_url": url,
        }
        print(f"OK {filename} {width}x{height} ratio={ratio:.3f}")

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
