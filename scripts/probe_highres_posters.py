from __future__ import annotations

import base64
import io

import requests
from PIL import Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
}

ASSETS = {
    "anpanman-pantan-2026-hq.webp": {
        "url": "https://news.anpan-movie.com/wp-content/uploads/2026/02/%E3%80%90RGB%E3%80%91%E6%9C%AC%E3%83%9D%E3%82%B9%E3%82%BF%E3%83%BC.jpg",
        "max_size": (1460, 2064),
        "quality": 86,
    },
    "kusuriya-movie-tw-20270129-hq.webp": {
        "url": "https://scontent-tpe1-1.cdninstagram.com/v/t51.82787-15/818424443_17989503228104272_8688352631772892243_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=104&ig_cache_key=Mzk5NTM4MzUzOTk3MzAxNjQ1NA%3D%3D.3-ccb7-5&ccb=7-5&_nc_sid=58cdad&efg=eyJ2ZW5jb2RlX3RhZyI6IkZFRUQueHBpZHMuMjg5NC5zZHIucmVndWxhcl9waG90by5DMyJ9&_nc_ohc=x7pQ1AqerTcQ7kNvwGPcoeN&_nc_oc=AdqWYEN6GR9a7dJd24vQ7QK_0kXacutRkKYBA8mSNylJiBpbO970xPgHfC-FuhSiOyv6n8ZfUpfrm3jmHdj0gzcV&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=scontent-tpe1-1.cdninstagram.com&_nc_gid=5yasYEueWgt5ATp7YllsYA&_nc_ss=7a22e&oh=00_AQNfBQGwIh6jOeKkariTiuKPdl61UsFhrZS1JenhZHOuPQ&oe=6ABFC08E",
        "max_size": (1447, 2048),
        "quality": 86,
    },
    "eupho-final-part1-tw.webp": {
        "url": "https://i.mopix.cc/2IyNun.jpg",
        "max_size": (897, 1280),
        "quality": 90,
    },
}

CHUNK = 20000


def encode_asset(name: str, cfg: dict) -> None:
    r = requests.get(cfg["url"], headers=HEADERS, timeout=45)
    print("SOURCE", name, r.status_code, r.headers.get("content-type"), len(r.content))
    r.raise_for_status()
    image = Image.open(io.BytesIO(r.content)).convert("RGB")
    original = image.size
    image.thumbnail(cfg["max_size"], Image.Resampling.LANCZOS)

    out = io.BytesIO()
    image.save(out, "WEBP", quality=cfg["quality"], method=6)
    payload = out.getvalue()
    encoded = base64.b64encode(payload).decode("ascii")
    print("READY", name, f"original={original[0]}x{original[1]}", f"output={image.width}x{image.height}", f"bytes={len(payload)}", f"b64={len(encoded)}")
    for idx in range(0, len(encoded), CHUNK):
        part = idx // CHUNK
        print(f"B64::{name}::{part:04d}::{encoded[idx:idx+CHUNK]}")
    print(f"B64END::{name}::{(len(encoded)+CHUNK-1)//CHUNK}")


def main() -> int:
    for name, cfg in ASSETS.items():
        encode_asset(name, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
