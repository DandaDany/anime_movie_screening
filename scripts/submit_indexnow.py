"""Submit deployed crawlable URLs to IndexNow.

The verification key is public by design and is hosted by GitHub Pages at the
site prefix. Submission failures should not block a successful site deploy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
SITE_ROOT = "https://dandadany.github.io/anime_movie_screening/"
INDEXNOW_KEY = "836c466d1aa7e23aa7c824b5c66d8581"
KEY_LOCATION = SITE_ROOT + INDEXNOW_KEY + ".txt"


def sitemap_urls(path: Path) -> list[str]:
    root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    for node in root.findall("sm:url/sm:loc", namespace):
        value = (node.text or "").strip()
        if value and value not in urls:
            urls.append(value)
    return urls


def build_payload(urls: list[str]) -> dict:
    host = urlparse(SITE_ROOT).netloc
    filtered = [
        url for url in urls
        if urlparse(url).scheme in {"http", "https"} and urlparse(url).netloc == host
    ]
    return {
        "host": host,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": filtered,
    }


def submit(payload: dict, endpoint: str = INDEXNOW_ENDPOINT, timeout: int = 20) -> int:
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "movie-showtimes-indexnow/1.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        status = int(response.status)
    if status not in {200, 202}:
        raise RuntimeError(f"IndexNow returned HTTP {status}")
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Notify IndexNow after GitHub Pages deployment.")
    parser.add_argument("--sitemap", type=Path, default=Path("web/sitemap.xml"))
    parser.add_argument("--endpoint", default=INDEXNOW_ENDPOINT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    urls = sitemap_urls(args.sitemap)
    payload = build_payload(urls)
    if not payload["urlList"]:
        raise SystemExit("IndexNow: sitemap contains no URLs for the configured host.")

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    status = submit(payload, endpoint=args.endpoint)
    print(f"IndexNow accepted {len(payload['urlList'])} URLs (HTTP {status}).")


if __name__ == "__main__":
    main()
