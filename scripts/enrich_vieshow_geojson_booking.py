#!/usr/bin/env python3
"""Enrich existing map GeoJSON with exact VIESHOW per-session booking URLs.

This is a lightweight repair/publish path. It does not re-crawl other cinemas.
It reads the already-published showtimes, resolves each VIESHOW movie/location
against VIESHOW's public quick-booking API in a browser context, and only
replaces booking_url when date + time (+ format when needed) match safely.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from playwright.sync_api import sync_playwright

from fetch_movie_showtimes import (
    VIESHOW_URL,
    _vieshow_quick_booking_sessions,
    normalize_text,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_GEOJSON = REPO / "web" / "data" / "locations.geojson"
DEFAULT_MASTER = REPO / "data" / "control" / "cinema_master.json"


def is_vieshow(props: dict) -> bool:
    haystack = " ".join(
        str(props.get(key) or "")
        for key in ("chain_name", "location_name", "map_name")
    )
    upper = haystack.upper()
    return "威秀" in haystack or "VIESHOW" in upper or "MUVIE" in upper


def master_location_codes(payload: dict) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in payload.get("locations") or []:
        try:
            location_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        code = str(item.get("source_location_code") or "").strip()
        if code:
            result[location_id] = code
    return result


def collect_feature_refs(payload: dict) -> list[tuple[dict, str]]:
    """Collect feature dict references with the best available movie-title hint."""
    refs: list[tuple[dict, str]] = []
    seen: set[int] = set()

    def add(feature: dict, hint: str = "") -> None:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            return
        marker = id(feature)
        if marker in seen:
            return
        seen.add(marker)
        props = feature.get("properties") or {}
        title = str(props.get("movie_title") or hint or "").strip()
        refs.append((feature, title))

    for title, by_date in (payload.get("movie_features_by_date") or {}).items():
        if not isinstance(by_date, dict):
            continue
        for features in by_date.values():
            for feature in features if isinstance(features, list) else []:
                add(feature, str(title))

    for title, features in (payload.get("movie_features") or {}).items():
        for feature in features if isinstance(features, list) else []:
            add(feature, str(title))

    for feature in payload.get("features") or []:
        add(feature, str(payload.get("movie_title") or ""))

    return refs


def choose_booking_url(showtime: dict, candidates: list[dict[str, str]]) -> str | None:
    show_date = str(showtime.get("show_date") or "").strip()
    start_time = str(showtime.get("time") or showtime.get("start_time") or "").strip().zfill(5)
    matching = [
        item
        for item in candidates
        if item.get("show_date") == show_date
        and item.get("start_time") == start_time
    ]
    if not matching:
        return None
    if len(matching) == 1:
        return matching[0].get("booking_url") or None

    record_norm = normalize_text(
        " ".join(
            str(showtime.get(key) or "")
            for key in ("format", "label", "auditorium")
        )
    )
    scored: list[tuple[int, dict[str, str]]] = []
    for item in matching:
        movie_norm = normalize_text(item.get("movie_text"))
        score = 0
        if movie_norm and movie_norm in record_norm:
            score = 3
        elif record_norm and record_norm in movie_norm:
            score = 2
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        # Do not guess when two same-time formats are equally plausible.
        return None
    return scored[0][1].get("booking_url") or None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    raw_text = args.input.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    master = json.loads(args.master.read_text(encoding="utf-8"))
    codes = master_location_codes(master)

    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    skipped_no_title = 0
    skipped_no_code = 0

    for feature, title in collect_feature_refs(payload):
        props = feature.get("properties") or {}
        if not is_vieshow(props):
            continue
        showtimes = props.get("showtimes") or []
        if not showtimes:
            continue
        try:
            location_id = int(props.get("location_id"))
        except (TypeError, ValueError):
            continue
        if not title:
            skipped_no_title += 1
            continue
        if location_id not in codes:
            skipped_no_code += 1
            continue
        groups[(title, location_id)].append(feature)

    resolved_groups = 0
    updated = 0
    total_vieshow_showtimes = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=40 if args.headed else 0)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(VIESHOW_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3000)

        for index, ((title, location_id), features) in enumerate(groups.items(), start=1):
            code = codes[location_id]
            try:
                candidates = _vieshow_quick_booking_sessions(page, code, [title])
            except Exception as exc:
                print(
                    f"[VIESHOW GEOJSON] {index}/{len(groups)} {code} {title}: "
                    f"lookup failed: {type(exc).__name__}: {exc}"
                )
                continue

            if candidates:
                resolved_groups += 1

            group_updated = 0
            for feature in features:
                props = feature.get("properties") or {}
                feature_date = str(props.get("show_date") or "").strip()
                for showtime in props.get("showtimes") or []:
                    total_vieshow_showtimes += 1
                    if not showtime.get("show_date") and feature_date:
                        showtime["show_date"] = feature_date
                    booking_url = choose_booking_url(showtime, candidates)
                    if not booking_url:
                        continue
                    if showtime.get("booking_url") != booking_url:
                        showtime["booking_url"] = booking_url
                        updated += 1
                        group_updated += 1

            print(
                f"[VIESHOW GEOJSON] {index}/{len(groups)} {code} {title}: "
                f"sessions={len(candidates)} updated={group_updated}"
            )

        context.close()
        browser.close()

    # Keep the repository's existing formatting style to avoid a giant cosmetic diff.
    if raw_text.count("\n") > 20:
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        output = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    args.input.write_text(output, encoding="utf-8")

    print(
        json.dumps(
            {
                "groups": len(groups),
                "resolved_groups": resolved_groups,
                "vieshow_showtimes_seen": total_vieshow_showtimes,
                "booking_urls_updated": updated,
                "skipped_no_title": skipped_no_title,
                "skipped_no_code": skipped_no_code,
            },
            ensure_ascii=False,
        )
    )

    if groups and updated == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
