from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "web" / "data" / "movie_posters.json"
WEB_DIR = ROOT / "web"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)
MAX_BYTES = 12 * 1024 * 1024


def _request(url: str, *, accept: str, timeout: int = 25) -> tuple[bytes, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7,ja;q=0.6",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"response too large: {url}")
        return data, content_type


def _srcset_urls(value: str) -> list[str]:
    urls: list[str] = []
    for part in str(value or "").split(","):
        token = part.strip().split(" ", 1)[0].strip()
        if token:
            urls.append(token)
    return list(reversed(urls))


def _extract_image_urls(page_url: str, html: bytes, needle: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    needle_fold = needle.casefold().strip()
    matches: list[str] = []
    for img in soup.find_all("img"):
        label = " ".join(
            str(img.get(key) or "")
            for key in ("alt", "title", "aria-label")
        ).casefold()
        if needle_fold and needle_fold not in label:
            continue

        raw_urls: list[str] = []
        for attr in ("data-src", "data-original", "data-lazy-src", "src"):
            value = str(img.get(attr) or "").strip()
            if value:
                raw_urls.append(value)
        for attr in ("data-srcset", "srcset"):
            raw_urls.extend(_srcset_urls(str(img.get(attr) or "")))

        for raw in raw_urls:
            if raw.startswith("data:"):
                continue
            absolute = urllib.parse.urljoin(page_url, raw)
            if absolute.startswith(("https://", "http://")) and absolute not in matches:
                matches.append(absolute)
    return matches


def _download_and_convert(url: str, target: Path) -> tuple[int, int]:
    data, content_type = _request(url, accept="image/avif,image/webp,image/apng,image/*,*/*;q=0.8")
    if content_type and not content_type.startswith("image/"):
        raise ValueError(f"not an image ({content_type}): {url}")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            if width < 250 or height < 350:
                raise ValueError(f"image too small {width}x{height}: {url}")
            if height <= width * 1.12:
                raise ValueError(f"not portrait poster-shaped {width}x{height}: {url}")
            rgb = image.convert("RGB")
            if width > 1200 or height > 1800:
                rgb.thumbnail((1200, 1800), Image.Resampling.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            rgb.save(tmp, format="JPEG", quality=90, optimize=True, progressive=True)
            tmp.replace(target)
            return width, height
    except UnidentifiedImageError as exc:
        raise ValueError(f"unreadable image: {url}") from exc


def cache_catalog(*, require: bool) -> int:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    failures: list[str] = []
    cached = 0

    for item in payload.get("movies", []):
        cfg = item.get("poster_cache")
        if not isinstance(cfg, dict):
            continue

        title = str(item.get("title") or "").strip()
        poster_path = str(item.get("poster_url") or "").strip()
        if not poster_path.startswith("assets/posters/") or not poster_path.endswith(".jpg"):
            failures.append(f"{title}: poster_url must be local assets/posters/*.jpg when poster_cache is used")
            continue

        target = WEB_DIR / poster_path
        if target.exists():
            target.unlink()

        source_page = str(cfg.get("source_page_url") or "").strip()
        needle = str(cfg.get("image_alt_contains") or "").strip()
        candidates: list[str] = []

        if source_page and needle:
            try:
                html, _ = _request(source_page, accept="text/html,application/xhtml+xml")
                candidates.extend(_extract_image_urls(source_page, html, needle))
            except Exception as exc:
                print(f"poster cache source-page warning [{title}]: {exc}", file=sys.stderr)

        for url in cfg.get("fallback_image_urls") or []:
            text = str(url or "").strip()
            if text.startswith("https://") and text not in candidates:
                candidates.append(text)

        if not candidates:
            failures.append(f"{title}: no image candidates")
            continue

        errors: list[str] = []
        for candidate in candidates:
            try:
                width, height = _download_and_convert(candidate, target)
                print(f"cached poster [{title}] {width}x{height} <- {candidate}")
                cached += 1
                break
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        else:
            failures.append(f"{title}: all candidates failed | " + " | ".join(errors))

    if failures:
        for failure in failures:
            print(f"poster cache ERROR: {failure}", file=sys.stderr)
        if require:
            raise SystemExit(1)

    print(f"poster cache: {cached} cached, {len(failures)} failed")
    return cached


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache fragile poster sources into the Pages artifact.")
    parser.add_argument("--require", action="store_true", help="fail if any configured poster cannot be cached")
    args = parser.parse_args()
    cache_catalog(require=args.require)


if __name__ == "__main__":
    main()
