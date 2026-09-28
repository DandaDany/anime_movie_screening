from __future__ import annotations

import io
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

SOURCES = [
    ("fma_tw_vieshow", "https://www.vscinemas.com.tw/film/detail.aspx?id=8976"),
    ("jinroh_tw_nownews", "https://www.nownews.com/news/6876853"),
    ("jinroh_tw_gnn", "https://gnn.gamer.com.tw/detail.php?sn=311969"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
}

def probe_image(session: requests.Session, url: str) -> tuple[int, str, int, int] | None:
    try:
        response = session.get(url, headers=HEADERS, timeout=20)
        ctype = response.headers.get("content-type", "")
        if response.status_code != 200 or "image" not in ctype:
            return None
        image = Image.open(io.BytesIO(response.content))
        return response.status_code, ctype, image.width, image.height
    except Exception:
        return None

def main() -> int:
    session = requests.Session()
    for label, page_url in SOURCES:
        response = session.get(page_url, headers=HEADERS, timeout=30)
        print(f"PAGE {label} status={response.status_code} url={response.url} ctype={response.headers.get('content-type')}")
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        seen = set()
        candidates = []
        for tag in soup.find_all("img"):
            raw = tag.get("src") or tag.get("data-src") or tag.get("data-original") or ""
            if not raw:
                continue
            url = urljoin(response.url, raw)
            if url in seen:
                continue
            seen.add(url)
            meta = probe_image(session, url)
            if not meta:
                continue
            _, ctype, width, height = meta
            ratio = width / height if height else 999
            alt = " ".join(str(tag.get("alt") or "").split())
            candidates.append((abs(ratio - (2/3)), -(width*height), url, ctype, width, height, ratio, alt))
        candidates.sort()
        for _, _, url, ctype, width, height, ratio, alt in candidates[:20]:
            print(
                f"IMG {label} {width}x{height} ratio={ratio:.3f} ctype={ctype} alt={alt!r} url={url}"
            )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
