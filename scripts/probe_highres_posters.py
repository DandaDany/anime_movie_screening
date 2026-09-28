from __future__ import annotations

import io
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Referer": "https://www.google.com/",
}

DIRECT = [
    (
        "eupho_keihan_movie_poster",
        "https://www.keihan.co.jp/euphonium/assets/img/img_tv.jpg",
    ),
    (
        "anpan_official",
        "https://news.anpan-movie.com/wp-content/uploads/2026/02/%E3%80%90RGB%E3%80%91%E6%9C%AC%E3%83%9D%E3%82%B9%E3%82%BF%E3%83%BC.jpg",
    ),
    (
        "kusuriya_user",
        "https://scontent-tpe1-1.cdninstagram.com/v/t51.82787-15/818424443_17989503228104272_8688352631772892243_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=104&ig_cache_key=Mzk5NTM4MzUzOTk3MzAxNjQ1NA%3D%3D.3-ccb7-5&ccb=7-5&_nc_sid=58cdad&efg=eyJ2ZW5jb2RlX3RhZyI6IkZFRUQueHBpZHMuMjg5NC5zZHIucmVndWxhcl9waG90by5DMyJ9&_nc_ohc=x7pQ1AqerTcQ7kNvwGPcoeN&_nc_oc=AdqWYEN6GR9a7dJd24vQ7QK_0kXacutRkKYBA8mSNylJiBpbO970xPgHfC-FuhSiOyv6n8ZfUpfrm3jmHdj0gzcV&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=scontent-tpe1-1.cdninstagram.com&_nc_gid=5yasYEueWgt5ATp7YllsYA&_nc_ss=7a22e&oh=00_AQNfBQGwIh6jOeKkariTiuKPdl61UsFhrZS1JenhZHOuPQ&oe=6ABFC08E",
    ),
]

PAGES = [
    (
        "eupho_ambassador",
        "https://www.ambassador.com.tw/home/MovieContent?DT=2026%2F09%2F03&MID=1f5dfea4-8e4e-47c9-99c2-dec31b681d70",
    ),
    (
        "eupho_shochiku",
        "https://www.shochiku.co.jp/cinema/lineup/%E3%80%8E%E6%9C%80%E7%B5%82%E6%A5%BD%E7%AB%A0-%E9%9F%BF%E3%81%91%EF%BC%81%E3%83%A6%E3%83%BC%E3%83%95%E3%82%A9%E3%83%8B%E3%82%A2%E3%83%A0-%E5%89%8D%E7%B7%A8%E3%80%8F/",
    ),
    ("eupho_official", "https://anime-eupho.com/"),
]


def probe(session: requests.Session, url: str):
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "image" not in ctype:
            return None
        image = Image.open(io.BytesIO(r.content))
        return len(r.content), image.width, image.height, ctype
    except Exception:
        return None


def main() -> int:
    s = requests.Session()

    for label, url in DIRECT:
        r = s.get(url, headers=HEADERS, timeout=45)
        print("DIRECT", label, "status", r.status_code, "ctype", r.headers.get("content-type"), "bytes", len(r.content))
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        print("DIRECT_IMAGE", label, img.width, img.height, round(img.width / img.height, 4), url)

    for label, page_url in PAGES:
        try:
            r = s.get(page_url, headers=HEADERS, timeout=45)
            print("PAGE", label, "status", r.status_code, "url", r.url, "bytes", len(r.content))
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as exc:
            print("PAGE_ERROR", label, type(exc).__name__, exc)
            continue
        seen = set()
        candidates = []
        for tag in soup.find_all("img"):
            raw = (
                tag.get("src")
                or tag.get("data-src")
                or tag.get("data-original")
                or tag.get("data-lazy-src")
                or ""
            )
            if not raw:
                continue
            url = urljoin(r.url, raw)
            if url in seen:
                continue
            seen.add(url)
            meta = probe(s, url)
            if not meta:
                continue
            size, w, h, ctype = meta
            if w < 300 or h < 300:
                continue
            ratio = w / h
            alt = " ".join(str(tag.get("alt") or "").split())
            candidates.append((abs(ratio - 0.707), -(w*h), url, size, w, h, ratio, alt, ctype))
        candidates.sort()
        for _, _, url, size, w, h, ratio, alt, ctype in candidates[:30]:
            print(
                "CANDIDATE", label,
                f"{w}x{h}", f"ratio={ratio:.4f}", f"bytes={size}",
                f"ctype={ctype}", f"alt={alt!r}", f"url={url}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
