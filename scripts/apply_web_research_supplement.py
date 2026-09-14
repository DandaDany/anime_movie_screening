from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import control_data
from showtime_availability import MAX_SOURCE_LOOKAHEAD_DAYS
from supplemental_web_update import merge_records_into_geojson

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH = PROJECT_DIR / "data" / "control" / "web_research_supplement.json"
DEFAULT_GEOJSON = PROJECT_DIR / "web" / "data" / "locations.geojson"
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def valid_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_research_records(payload: dict, *, master: dict, movies: list[dict]) -> tuple[str, dict]:
    if payload.get("schema_version") != 1:
        raise ValueError("web research supplement schema_version must be 1")
    for_date = date.fromisoformat(str(payload.get("for_date"))).isoformat()
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("web research supplement records must be a list")

    allowed_titles = {movie["title"] for movie in movies}
    active_locations = {
        int(location["id"]): location
        for location in master["locations"]
        if location.get("active")
    }
    start = date.fromisoformat(for_date)
    end = start + timedelta(days=MAX_SOURCE_LOOKAHEAD_DAYS)
    normalized: dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]] = {}

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record[{index}] must be an object")
        location_id = int(record.get("location_id"))
        if location_id not in active_locations:
            raise ValueError(f"record[{index}] references inactive/missing location_id={location_id}")
        movie_title = str(record.get("movie_title") or "").strip()
        if movie_title not in allowed_titles:
            raise ValueError(f"record[{index}] movie is not eligible today: {movie_title!r}")
        show_date = date.fromisoformat(str(record.get("show_date"))).isoformat()
        parsed_date = date.fromisoformat(show_date)
        if parsed_date < start or parsed_date > end:
            raise ValueError(
                f"record[{index}] show_date {show_date} outside {for_date}..{end.isoformat()}"
            )
        source_url = str(record.get("source_url") or "").strip()
        if not valid_http_url(source_url):
            raise ValueError(f"record[{index}] requires a valid http(s) source_url")
        evidence = str(record.get("evidence") or "").strip()
        if not evidence:
            raise ValueError(f"record[{index}] requires concise evidence text")
        showtimes = record.get("showtimes")
        if not isinstance(showtimes, list) or not showtimes:
            raise ValueError(f"record[{index}] showtimes must be a non-empty list")

        normalized_times: list[dict[str, str | None]] = []
        seen_times: set[str] = set()
        for showtime_index, item in enumerate(showtimes):
            if not isinstance(item, dict):
                raise ValueError(f"record[{index}].showtimes[{showtime_index}] must be an object")
            clock = str(item.get("time") or "").strip()
            if not TIME_RE.fullmatch(clock):
                raise ValueError(f"record[{index}] invalid showtime: {clock!r}")
            if clock in seen_times:
                continue
            seen_times.add(clock)
            normalized_times.append(
                {
                    "time": clock,
                    "format": str(item.get("format")).strip() if item.get("format") else None,
                    "language": str(item.get("language")).strip() if item.get("language") else None,
                    "auditorium": str(item.get("auditorium")).strip() if item.get("auditorium") else None,
                }
            )

        key = (movie_title, show_date, location_id)
        if key in normalized:
            existing_source, existing_times = normalized[key]
            if existing_source != source_url:
                # Multiple corroborating sources are fine, but keep one canonical booking/source URL.
                source_url = existing_source
            existing_clock = {item["time"] for item in existing_times}
            existing_times.extend(item for item in normalized_times if item["time"] not in existing_clock)
            existing_times.sort(key=lambda item: item["time"] or "")
            normalized[key] = (source_url, existing_times)
        else:
            normalized[key] = (source_url, sorted(normalized_times, key=lambda item: item["time"] or ""))

    return for_date, normalized


def apply_research(research_path: Path, geojson_path: Path, *, dry_run: bool = False) -> tuple[int, int, int]:
    payload = load_json(research_path)
    master = control_data.load_cinema_master()
    for_date_raw = str(payload.get("for_date") or "")
    primary_date = date.fromisoformat(for_date_raw).isoformat()
    tracked = control_data.load_tracked_movies()
    movies = control_data.eligible_movies(tracked, date.fromisoformat(primary_date))
    primary_date, records = normalize_research_records(payload, master=master, movies=movies)
    geojson = load_json(geojson_path)
    geojson, features_added, showtimes_added = merge_records_into_geojson(
        geojson,
        primary_date=primary_date,
        movies=movies,
        records=records,
        master=master,
    )
    print(
        f"[web research supplement] records={len(records)} "
        f"features_added={features_added} showtimes_added={showtimes_added}"
    )
    if not dry_run:
        tmp = geojson_path.with_suffix(geojson_path.suffix + ".tmp")
        tmp.write_text(json.dumps(geojson, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(geojson_path)
    return len(records), features_added, showtimes_added


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and merge the 06:00 ChatGPT web-research supplement into map GeoJSON.")
    parser.add_argument("--research", type=Path, default=DEFAULT_RESEARCH)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    research_path = args.research if args.research.is_absolute() else PROJECT_DIR / args.research
    geojson_path = args.geojson if args.geojson.is_absolute() else PROJECT_DIR / args.geojson
    apply_research(research_path, geojson_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
