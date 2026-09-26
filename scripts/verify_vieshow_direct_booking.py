#!/usr/bin/env python3
"""Fail closed when VIESHOW showtimes lose direct per-session booking URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "web" / "data" / "locations.geojson"


def is_vieshow_feature(feature: dict) -> bool:
    props = feature.get("properties") or {}
    haystack = " ".join(
        str(props.get(key) or "")
        for key in ("chain_name", "location_name", "map_name")
    )
    return "威秀" in haystack or "VIESHOW" in haystack.upper() or "MUVIE" in haystack.upper()


def is_direct_booking(url: str | None) -> bool:
    value = str(url or "")
    return (
        "vscinemas.com.tw/vsTicketing/ticketing/booking.aspx" in value
        and "txtSessionId=" in value
        and "cinemacode=" in value
    )


def published_features(payload: dict):
    """Yield the feature collection actually consumed by the frontend.

    Multi-movie exports use movie_features_by_date; older/single-movie exports
    fall back to movie_features or top-level features.
    """
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


def inspect(payload: dict) -> dict[str, int]:
    vieshow_showtimes = 0
    direct_showtimes = 0
    venues: set[tuple[object, object]] = set()

    for feature in published_features(payload):
        if not is_vieshow_feature(feature):
            continue
        props = feature.get("properties") or {}
        showtimes = props.get("showtimes") or []
        if showtimes:
            venues.add((props.get("location_id"), props.get("show_date")))
        for showtime in showtimes:
            vieshow_showtimes += 1
            if is_direct_booking(showtime.get("booking_url")):
                direct_showtimes += 1

    return {
        "vieshow_venues": len(venues),
        "vieshow_showtimes": vieshow_showtimes,
        "direct_booking_showtimes": direct_showtimes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    stats = inspect(payload)
    print(json.dumps(stats, ensure_ascii=False))

    # If the tracked movie set has no VIESHOW sessions today, this check is not applicable.
    if stats["vieshow_showtimes"] == 0:
        print("[VIESHOW VERIFY] no VIESHOW showtimes in current dataset; skip direct-link assertion")
        return 0

    if stats["direct_booking_showtimes"] == 0:
        print(
            "[VIESHOW VERIFY] ERROR: VIESHOW showtimes exist but none contain a direct "
            "booking URL with cinemacode + txtSessionId."
        )
        return 2

    print(
        "[VIESHOW VERIFY] direct booking links present: "
        f"{stats['direct_booking_showtimes']}/{stats['vieshow_showtimes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
