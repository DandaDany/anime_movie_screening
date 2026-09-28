from __future__ import annotations

import io
from pathlib import Path

import requests
from PIL import Image

URL = """https://scontent-tpe1-1.cdninstagram.com/v/t51.82787-15/818424443_17989503228104272_8688352631772892243_n.jpg?stp=dst-jpg_e35_tt6&_nc_cat=104&ig_cache_key=Mzk5NTM4MzUzOTk3MzAxNjQ1NA%3D%3D.3-ccb7-5&ccb=7-5&_nc_sid=58cdad&efg=eyJ2ZW5jb2RlX3RhZyI6IkZFRUQueHBpZHMuMjg5NC5zZHIucmVndWxhcl9waG90by5DMyJ9&_nc_ohc=x7pQ1AqerTcQ7kNvwGPcoeN&_nc_oc=AdqWYEN6GR9a7dJd24vQ7QK_0kXacutRkKYBA8mSNylJiBpbO970xPgHfC-FuhSiOyv6n8ZfUpfrm3jmHdj0gzcV&_nc_ad=z-m&_nc_cid=0&_nc_zt=23&_nc_ht=scontent-tpe1-1.cdninstagram.com&_nc_gid=5yasYEueWgt5ATp7YllsYA&_nc_ss=7a22e&oh=00_AQNfBQGwIh6jOeKkariTiuKPdl61UsFhrZS1JenhZHOuPQ&oe=6ABFC08E"""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Referer": "https://www.instagram.com/",
}


def main() -> int:
    response = requests.get(URL, headers=HEADERS, timeout=45)
    print("status", response.status_code, "ctype", response.headers.get("content-type"), "bytes", len(response.content))
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))
    image.verify()
    image = Image.open(io.BytesIO(response.content))
    print("image", image.width, image.height, image.mode)
    if image.width < 300 or image.height < 300:
        raise RuntimeError(f"image too small: {image.width}x{image.height}")
    out = Path("artifacts/kusuriya")
    out.mkdir(parents=True, exist_ok=True)
    (out / "kusuriya-user-source.jpg").write_bytes(response.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
