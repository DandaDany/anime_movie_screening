from __future__ import annotations

import io
from pathlib import Path

import requests
from PIL import Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
}

ASSETS = {
    "anpanman-official.jpg": "https://news.anpan-movie.com/wp-content/uploads/2026/02/%E3%80%90RGB%E3%80%91%E6%9C%AC%E3%83%9D%E3%82%B9%E3%82%BF%E3%83%BC.jpg",
    "kusuriya-user.jpg": "https://scontent-tpe1-1.cdninstagram.com/v/t51.82787-15/818424443_17989503228104272_8688352631772892243_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=104&ig_cache_key=Mzk5NTM4MzUzOTk3MzAxNjQ1NA%3D%3D.3-ccb7-5&ccb=7-5&_nc_sid=58cdad&efg=eyJ2ZW5jb2RlX3RhZyI6IkZFRUQueHBpZHMuMjg5NC5zZHIucmVndWxhcl9waG90by5DMyJ9&_nc_ohc=x7pQ1AqerTcQ7kNvwGPcoeN&_nc_oc=AdqWYEN6GR9a7dJd24vQ7QK_0kXacutRkKYBA8mSNylJiBpbO970xPgHfC-FuhSiOyv6n8ZfUpfrm3jmHdj0gzcV&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=scontent-tpe1-1.cdninstagram.com&_nc_gid=5yasYEueWgt5ATp7YllsYA&_nc_ss=7a22e&oh=00_AQNfBQGwIh6jOeKkariTiuKPdl61UsFhrZS1JenhZHOuPQ&oe=6ABFC08E",
    "eupho-shochiku-poster.jpg": "https://www.shochiku.co.jp/wp-content/uploads/2025/07/euph_saishu_kv2_ari4-scaled.jpg",
    "eupho-tw-1.jpg": "https://i.mopix.cc/2IyNun.jpg",
    "eupho-tw-2.jpg": "https://i.mopix.cc/7HY8Xl.jpg",
    "eupho-tw-3.jpg": "https://i.mopix.cc/FfObra.jpg",
    "eupho-tw-4.jpg": "https://i.mopix.cc/d5fW9j.jpg",
}

def main() -> int:
    out = Path("artifacts/highres")
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for name, url in ASSETS.items():
        try:
            r = session.get(url, headers=HEADERS, timeout=45)
            print("GET", name, r.status_code, r.headers.get("content-type"), len(r.content), url)
            if r.status_code != 200:
                continue
            img = Image.open(io.BytesIO(r.content))
            print("IMG", name, img.width, img.height, round(img.width / img.height, 4))
            (out / name).write_bytes(r.content)
        except Exception as exc:
            print("ERROR", name, type(exc).__name__, exc)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
