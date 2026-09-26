#!/usr/bin/env python3
"""Fetch static VIESHOW seat-preview snapshots for showtimes already in GeoJSON.

The public SessionSeats page is read-only but requires a real browser request with
a VIESHOW Referer. This script never logs in, selects tickets, clicks seats,
reserves, checks out, or pays.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "web" / "data" / "locations.geojson"
DEFAULT_OUTPUT = REPO / "web" / "data" / "vieshow_seat_previews.json"
VIESHOW_HOME = "https://www.vscinemas.com.tw/"
VIESHOW_BOOKING_PATH = "/vsTicketing/ticketing/booking.aspx"
VIESHOW_SEAT_BASE = "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--booking-url",
        action="append",
        default=[],
        help="Additional direct VIESHOW booking URL for testing (repeatable).",
    )
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def parse_booking_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.netloc.lower() != "www.vscinemas.com.tw":
        return None
    if parsed.path.lower() != VIESHOW_BOOKING_PATH.lower():
        return None
    query = parse_qs(parsed.query)
    cinema = (query.get("cinemacode") or [""])[0].strip()
    session = (query.get("txtSessionId") or [""])[0].strip()
    if not cinema or not session:
        return None
    return cinema, session


def seat_preview_url(cinema: str, session: str) -> str:
    return VIESHOW_SEAT_BASE + "?" + urlencode(
        {"cinemacode": cinema, "txtSessionId": session}
    )


def _published_features(payload: dict):
    by_date = payload.get("movie_features_by_date")
    if isinstance(by_date, dict) and by_date:
        for date_map in by_date.values():
            if not isinstance(date_map, dict):
                continue
            for features in date_map.values():
                for feature in features if isinstance(features, list) else []:
                    yield feature
        return

    movie_features = payload.get("movie_features")
    if isinstance(movie_features, dict) and movie_features:
        for features in movie_features.values():
            for feature in features if isinstance(features, list) else []:
                yield feature
        return

    for feature in payload.get("features") or []:
        yield feature


def collect_booking_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for feature in _published_features(payload):
        props = feature.get("properties") or {}
        for showtime in props.get("showtimes") or []:
            url = str(showtime.get("booking_url") or "").strip()
            if parse_booking_url(url):
                found.add(url)
    return sorted(found)


def text_of(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def parse_preview_html(html: str, cinema: str, session: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    grid = soup.select_one("#GridViewSessionSeats")
    if not grid:
        return None

    rows: list[list[dict[str, str]]] = []
    available = 0
    sold = 0
    wheelchair = 0

    for tr in grid.select("tr"):
        row: list[dict[str, str]] = []
        for td in tr.find_all("td", recursive=False):
            label = td.select_one(".label[data-toggle='tooltip'][title]")
            if label:
                seat_id = str(label.get("title") or "").strip()
                classes = set(label.get("class") or [])
                if "label-danger" in classes:
                    status = "sold"
                    sold += 1
                else:
                    status = "available"
                    available += 1
                row.append({"type": status, "seat": seat_id})
                continue

            image = td.find("img")
            src = str(image.get("src") or "") if image else ""
            low = src.lower()
            if "wheelchair" in low:
                wheelchair += 1
                row.append({
                    "type": "wheelchair",
                    "seat": str(image.get("title") or image.get("alt") or "").strip(),
                })
            else:
                row.append({"type": "gap", "seat": ""})
        if row:
            rows.append(row)

    ordinary = available + sold
    now = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    return {
        "key": f"{cinema}:{session}",
        "cinemacode": cinema,
        "session_id": session,
        "source_url": seat_preview_url(cinema, session),
        "fetched_at": now,
        "movie": text_of(soup, "#LabelMovie_strName"),
        "movie_en": text_of(soup, "#LabelMovie_strNameEn"),
        "datetime": text_of(soup, "#LabelSession_dtmDateTime"),
        "cinema": text_of(soup, "#LabelCinema_strName"),
        "auditorium": text_of(soup, "#LabelScreen_strName"),
        "ordinary_seats": ordinary,
        "available": available,
        "sold": sold,
        "wheelchair": wheelchair,
        "rows": rows,
    }


def main() -> int:
    args = parse_args()
    urls = set(collect_booking_urls(args.input))
    urls.update(url for url in args.booking_url if parse_booking_url(url))

    previews: dict[str, dict] = {}
    failures: list[dict[str, str]] = []

    if urls:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            context = browser.new_context(
                locale="zh-TW",
                timezone_id="Asia/Taipei",
                user_agent=UA,
                viewport={"width": 1366, "height": 900},
            )
            page = context.new_page()

            for index, booking_url in enumerate(sorted(urls), start=1):
                parsed = parse_booking_url(booking_url)
                if not parsed:
                    continue
                cinema, session = parsed
                url = seat_preview_url(cinema, session)
                try:
                    response = page.goto(
                        url,
                        referer=VIESHOW_HOME,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    page.wait_for_timeout(450)
                    if not response or response.status != 200:
                        raise RuntimeError(
                            f"unexpected HTTP status {response.status if response else 'none'}"
                        )
                    preview = parse_preview_html(page.content(), cinema, session)
                    if not preview:
                        raise RuntimeError(
                            f"seat grid missing; final_url={page.url!r} title={page.title()!r}"
                        )
                    previews[preview["key"]] = preview
                    print(
                        f"[VIESHOW SEATS] {index}/{len(urls)} {preview['key']} "
                        f"available={preview['available']} sold={preview['sold']}"
                    )
                except Exception as exc:
                    failures.append({
                        "booking_url": booking_url,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                    print(
                        f"[VIESHOW SEATS] {index}/{len(urls)} {cinema}:{session} failed: {exc}"
                    )

            context.close()
            browser.close()

    payload = {
        "updated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "source": "VIESHOW public seat preview",
        "realtime": False,
        "preview_count": len(previews),
        "failure_count": len(failures),
        "previews": previews,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "booking_urls": len(urls),
                "previews": len(previews),
                "failures": len(failures),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )

    # A partial outage should not erase the rest of the map, but if explicit
    # test URLs were requested they are acceptance inputs and must succeed.
    if args.booking_url and len(previews) < len(
        {parse_booking_url(url) for url in args.booking_url if parse_booking_url(url)}
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
