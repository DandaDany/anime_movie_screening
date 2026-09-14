from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import control_data
from showtime_availability import MAX_SOURCE_LOOKAHEAD_DAYS
from supplemental_web_update import (
    fetch_bytes,
    html_lines,
    load_json,
    merge_records_into_geojson,
    page_has_requested_date,
    parse_atmovies_page,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GEOJSON = PROJECT_DIR / "web" / "data" / "locations.geojson"
DEFAULT_SOURCES = PROJECT_DIR / "data" / "input" / "supplemental_showtime_sources.json"
DEFAULT_SOCIAL_SOURCES = PROJECT_DIR / "data" / "input" / "social_showtime_sources.json"
TAIPEI = ZoneInfo("Asia/Taipei")
MADOU_LOCATION_ID = 104


def _madou_source(source_config: dict) -> dict:
    for source in source_config.get("sources", []):
        if int(source.get("location_id", -1)) == MADOU_LOCATION_ID:
            return source
    raise ValueError("麻豆戲院 location_id=104 is missing from supplemental source config")


def _candidate_templates(source: dict) -> list[str]:
    values = [source.get("url_template"), *(source.get("fallback_url_templates") or [])]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        template = str(value)
        if template in seen:
            continue
        seen.add(template)
        result.append(template)
    if not result:
        raise ValueError("麻豆戲院 has no deterministic @movies source template")
    return result


def _social_urls(social_config: dict | None) -> list[str]:
    if not social_config:
        return []
    for source in social_config.get("sources", []):
        if int(source.get("location_id", -1)) != MADOU_LOCATION_ID:
            continue
        urls = []
        if source.get("official_url"):
            urls.append(str(source["official_url"]))
        urls.extend(str(value) for value in (source.get("social_urls") or []) if value)
        return list(dict.fromkeys(urls))
    return []


def collect_madou_records(
    *,
    primary_date: str,
    movies: list[dict],
    source_config: dict,
    social_config: dict | None = None,
    fetcher=fetch_bytes,
) -> tuple[dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]], int, int]:
    """Recover Madou schedules through redundant @movies hosts.

    A host is considered usable only when the fetched page explicitly contains the
    requested date. A 2xx response that redirects to a stale/default date is not
    treated as a successful check. We stop at the first usable mirror for each date.

    If every configured @movies host fails or lacks the requested date, the run is
    reported as social-required. No empty result is interpreted as evidence that
    Madou has no sessions; the 07:00 research automation must then inspect the
    configured official Facebook/Instagram sources.
    """
    source = _madou_source(source_config)
    templates = _candidate_templates(source)
    social_urls = _social_urls(social_config)
    start = date.fromisoformat(primary_date)
    show_dates = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(MAX_SOURCE_LOOKAHEAD_DAYS + 1)
    ]

    records: dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]] = {}
    success = 0
    failure = 0

    for show_date in show_dates:
        compact_date = show_date.replace("-", "")
        usable = False
        diagnostics: list[str] = []
        for template in templates:
            url = template.format(date=compact_date)
            try:
                raw = fetcher(url)
            except Exception as exc:
                diagnostics.append(f"{url} => {type(exc).__name__}: {exc}")
                continue

            lines = html_lines(raw)
            if not page_has_requested_date(lines, show_date):
                diagnostics.append(f"{url} => requested date missing")
                continue

            parsed = parse_atmovies_page(raw, show_date, movies)
            usable = True
            success += 1
            found = sum(len(items) for items in parsed.values())
            if found:
                print(
                    f"[madou fallback] {show_date}: {found} tracked showtime(s) "
                    f"via {url}"
                )
            else:
                print(f"[madou fallback] {show_date}: verified page, no tracked showtimes via {url}")
            for movie_title, showtimes in parsed.items():
                if showtimes:
                    records[(movie_title, show_date, MADOU_LOCATION_ID)] = (url, showtimes)
            break

        if usable:
            continue

        failure += 1
        suffix = f" social={','.join(social_urls)}" if social_urls else ""
        print(
            f"[madou fallback][social-required] {show_date}: "
            f"all @movies hosts unavailable or stale; {' | '.join(diagnostics)}{suffix}"
        )

    return records, success, failure


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover 麻豆戲院 showtimes through redundant @movies hosts before social fallback."
    )
    parser.add_argument("--date", default=datetime.now(TAIPEI).date().isoformat())
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--social-sources", type=Path, default=DEFAULT_SOCIAL_SOURCES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    primary_date = date.fromisoformat(args.date).isoformat()
    geojson_path = args.geojson if args.geojson.is_absolute() else PROJECT_DIR / args.geojson
    sources_path = args.sources if args.sources.is_absolute() else PROJECT_DIR / args.sources
    social_path = (
        args.social_sources
        if args.social_sources.is_absolute()
        else PROJECT_DIR / args.social_sources
    )

    tracked = control_data.load_tracked_movies()
    movies = control_data.eligible_movies(tracked, date.fromisoformat(primary_date))
    master = control_data.load_cinema_master()
    source_config = load_json(sources_path)
    social_config = load_json(social_path) if social_path.exists() else None
    payload = load_json(geojson_path)

    records, success, failure = collect_madou_records(
        primary_date=primary_date,
        movies=movies,
        source_config=source_config,
        social_config=social_config,
    )

    if records:
        payload, features_added, showtimes_added = merge_records_into_geojson(
            payload,
            primary_date=primary_date,
            movies=movies,
            records=records,
            master=master,
        )
    else:
        features_added = 0
        showtimes_added = 0

    print(
        f"[madou fallback summary] dates ok/fail={success}/{failure} "
        f"features_added={features_added} showtimes_added={showtimes_added}"
    )
    if args.dry_run or not records:
        if args.dry_run:
            print("[madou fallback] dry-run; GeoJSON not written")
        return

    tmp = geojson_path.with_suffix(geojson_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(geojson_path)
    print(f"[madou fallback] updated {geojson_path}")


if __name__ == "__main__":
    main()
