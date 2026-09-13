from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import control_data
from movie_title_matching import movie_matches
from showtime_availability import MAX_SOURCE_LOOKAHEAD_DAYS


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GEOJSON = PROJECT_DIR / "web" / "data" / "locations.geojson"
DEFAULT_SOURCES = PROJECT_DIR / "data" / "input" / "supplemental_showtime_sources.json"
TAIPEI = ZoneInfo("Asia/Taipei")
TIME_RE = re.compile(r"^(\d{1,2})\s*[：:]\s*(\d{2})$")


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def fetch_bytes(url: str, *, attempts: int = 2, timeout: int = 20) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    }
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # source failures are non-destructive by design
            last_exc = exc
            if attempt < attempts:
                time.sleep(1)
    assert last_exc is not None
    raise last_exc


def html_lines(raw: bytes) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in soup.get_text("\n").splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]


def date_tokens(show_date: str) -> set[str]:
    value = date.fromisoformat(show_date)
    return {
        value.strftime("%Y/%m/%d"),
        f"{value.year}/{value.month}/{value.day}",
        value.strftime("%Y-%m-%d"),
        f"{value.month:02d}/{value.day:02d}",
        f"{value.month}/{value.day}",
    }


def page_has_requested_date(lines: list[str], show_date: str) -> bool:
    tokens = date_tokens(show_date)
    for line in lines:
        if any(token in line for token in tokens):
            return True
    return False


def infer_language(text: str) -> str | None:
    if any(token in text for token in ("國語", "中文", "中文版")):
        return "國語"
    if any(token in text for token in ("日語", "日文")):
        return "日語"
    if any(token in text for token in ("英語", "英文")):
        return "英語"
    return None


def parse_atmovies_page(
    raw: bytes,
    show_date: str,
    movies: list[dict],
) -> dict[str, list[dict[str, str | None]]]:
    """Extract tracked-title showtimes from one @movies theater/date page.

    We deliberately parse rendered text instead of fragile CSS classes.  A page is
    accepted only when it contains the requested date.  For each tracked title we
    collect only clock-only lines after a matching title and stop at the site's
    `其他戲院` / update boundary.  This makes a stale redirect fail closed instead
    of assigning today's sessions to the wrong date.
    """
    lines = html_lines(raw)
    if not page_has_requested_date(lines, show_date):
        return {}

    result: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    all_aliases = {
        movie["title"]: [movie["title"], *(movie.get("aliases") or [])]
        for movie in movies
    }

    for index, line in enumerate(lines):
        matched_title = None
        for title, aliases in all_aliases.items():
            if movie_matches(line, aliases):
                matched_title = title
                break
        if matched_title is None:
            continue

        source_title = line
        for follower in lines[index + 1 : index + 35]:
            if follower.startswith("其他戲院") or follower.startswith("更新時間"):
                break
            # Once another tracked title begins, the current movie block is over.
            if any(
                title != matched_title and movie_matches(follower, aliases)
                for title, aliases in all_aliases.items()
            ):
                break
            match = TIME_RE.fullmatch(follower)
            if not match:
                continue
            start_time = f"{int(match.group(1)):02d}:{match.group(2)}"
            key = (matched_title, start_time)
            if key in seen:
                continue
            seen.add(key)
            result[matched_title].append(
                {
                    "time": start_time,
                    "format": source_title,
                    "language": infer_language(source_title),
                    "auditorium": None,
                }
            )
    return dict(result)


def map_context(master: dict) -> tuple[dict[int, dict], dict[int, dict]]:
    chain_by_id = {chain["id"]: chain for chain in master["chains"]}
    location_by_id = {location["id"]: location for location in master["locations"]}
    return chain_by_id, location_by_id


def build_feature(
    *,
    movie_title: str,
    show_date: str,
    location: dict,
    chain: dict,
    source_url: str,
    showtimes: list[dict[str, str | None]],
) -> dict:
    normalized_showtimes = []
    for item in sorted(showtimes, key=lambda value: value["time"] or ""):
        time_value = str(item["time"])
        label_parts = [time_value]
        if item.get("format"):
            label_parts.append(str(item["format"]))
        normalized_showtimes.append(
            {
                "time": time_value,
                "format": item.get("format"),
                "language": item.get("language"),
                "auditorium": item.get("auditorium"),
                "booking_url": source_url,
                "label": " ".join(label_parts),
            }
        )
    map_name = location.get("display_name") or f"{chain['chain_name']} {location['location_name']}"
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [location["longitude"], location["latitude"]],
        },
        "properties": {
            "location_id": location["id"],
            "chain_name": chain["chain_name"],
            "location_name": location["location_name"],
            "map_name": map_name,
            "address": location.get("address"),
            "city": (location.get("city") or "").replace("台", "臺") or None,
            "location_url": location.get("location_url") or chain.get("official_url") or source_url,
            "official_url": chain.get("official_url"),
            "crawl_url": source_url,
            "movie_title": movie_title,
            "show_date": show_date,
            "showtime_count": len(normalized_showtimes),
            "showtimes": normalized_showtimes,
            "start_times": ", ".join(item["time"] for item in normalized_showtimes),
            "supplemental_web_source": True,
        },
    }


def merge_feature(existing: dict | None, incoming: dict) -> tuple[dict, int]:
    if existing is None:
        return incoming, len(incoming["properties"].get("showtimes") or [])

    props = existing.setdefault("properties", {})
    incoming_props = incoming["properties"]
    # A real supplemental result supersedes an unavailable placeholder for the same location.
    for key in ("showtime_unavailable", "showtime_unavailable_reason"):
        props.pop(key, None)
    for key in (
        "chain_name", "location_name", "map_name", "address", "city", "location_url",
        "official_url", "crawl_url", "movie_title", "show_date",
    ):
        props[key] = incoming_props.get(key)
    existing["geometry"] = incoming["geometry"]
    props["supplemental_web_source"] = True

    current = list(props.get("showtimes") or [])
    seen = {
        (
            item.get("time"), item.get("format"), item.get("language"), item.get("auditorium")
        )
        for item in current
    }
    added = 0
    for item in incoming_props.get("showtimes") or []:
        key = (item.get("time"), item.get("format"), item.get("language"), item.get("auditorium"))
        # Time is the strongest stable identity across first-party and fallback sources.
        time_already_present = any(existing_item.get("time") == item.get("time") for existing_item in current)
        if key in seen or time_already_present:
            continue
        current.append(item)
        seen.add(key)
        added += 1
    current.sort(key=lambda item: item.get("time") or "")
    props["showtimes"] = current
    props["showtime_count"] = len(current)
    props["start_times"] = ", ".join(str(item.get("time") or "") for item in current if item.get("time"))
    return existing, added


def real_showtimes(features: list[dict]) -> bool:
    return any((feature.get("properties") or {}).get("showtime_count", 0) > 0 for feature in features)


def merge_records_into_geojson(
    payload: dict,
    *,
    primary_date: str,
    movies: list[dict],
    records: dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]],
    master: dict,
) -> tuple[dict, int, int]:
    chain_by_id, location_by_id = map_context(master)
    movie_titles = [movie["title"] for movie in movies]
    by_date = payload.setdefault("movie_features_by_date", {})
    features_added = 0
    showtimes_added = 0

    # Drop past date buckets while preserving all current/future first-pass information.
    for title in list(by_date):
        if title not in movie_titles:
            by_date.pop(title, None)
            continue
        by_date[title] = {
            day: features
            for day, features in (by_date.get(title) or {}).items()
            if day >= primary_date
        }

    for title in movie_titles:
        by_date.setdefault(title, {})

    for (movie_title, show_date, location_id), (source_url, showtimes) in records.items():
        if not showtimes or movie_title not in by_date:
            continue
        location = location_by_id.get(location_id)
        if not location or not location.get("active"):
            continue
        chain = chain_by_id.get(location["chain_id"])
        if not chain or not chain.get("active"):
            continue
        incoming = build_feature(
            movie_title=movie_title,
            show_date=show_date,
            location=location,
            chain=chain,
            source_url=source_url,
            showtimes=showtimes,
        )
        day_features = list(by_date[movie_title].get(show_date) or [])
        existing_index = next(
            (
                index
                for index, feature in enumerate(day_features)
                if int((feature.get("properties") or {}).get("location_id", -1)) == location_id
            ),
            None,
        )
        if existing_index is None:
            day_features.append(incoming)
            features_added += 1
            showtimes_added += len(showtimes)
        else:
            merged, added = merge_feature(day_features[existing_index], incoming)
            day_features[existing_index] = merged
            showtimes_added += added
        day_features.sort(key=lambda feature: str((feature.get("properties") or {}).get("map_name") or ""))
        by_date[movie_title][show_date] = day_features

    movie_features = {}
    movies_meta = []
    all_available: set[str] = set()
    for title in movie_titles:
        title_dates = by_date.get(title) or {}
        primary_features = list(title_dates.get(primary_date) or [])
        movie_features[title] = primary_features
        available = sorted(day for day, features in title_dates.items() if real_showtimes(features))
        all_available.update(available)
        movies_meta.append(
            {
                "title": title,
                "show_date": primary_date,
                "available_dates": available,
                "feature_count": len(primary_features),
            }
        )

    payload["show_date"] = primary_date
    payload["movie_title"] = movie_titles[0] if movie_titles else None
    payload["movies"] = movies_meta
    payload["movie_features"] = movie_features
    payload["movie_features_by_date"] = by_date
    payload["available_dates"] = sorted(all_available)
    payload["features"] = movie_features.get(movie_titles[0], []) if movie_titles else []
    payload["feature_count"] = len(payload["features"])
    payload["updated_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    payload["supplemental_updated_at"] = payload["updated_at"]
    return payload, features_added, showtimes_added


def collect_records(
    *,
    primary_date: str,
    movies: list[dict],
    source_config: dict,
) -> tuple[dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]], int, int]:
    records: dict[tuple[str, str, int], tuple[str, list[dict[str, str | None]]]] = {}
    success = failure = 0
    start = date.fromisoformat(primary_date)
    show_dates = [(start + timedelta(days=offset)).isoformat() for offset in range(MAX_SOURCE_LOOKAHEAD_DAYS + 1)]

    for source in source_config.get("sources", []):
        if not source.get("enabled", True):
            continue
        location_id = int(source["location_id"])
        source_name = str(source.get("name") or location_id)
        for show_date in show_dates:
            compact_date = show_date.replace("-", "")
            url = str(source["url_template"]).format(date=compact_date)
            try:
                raw = fetch_bytes(url)
                parsed = parse_atmovies_page(raw, show_date, movies)
                success += 1
                found = sum(len(items) for items in parsed.values())
                if found:
                    print(f"[supplement] {source_name} {show_date}: {found} tracked showtime(s)")
                for movie_title, showtimes in parsed.items():
                    if showtimes:
                        records[(movie_title, show_date, location_id)] = (url, showtimes)
            except Exception as exc:
                failure += 1
                print(f"[supplement][degraded] {source_name} {show_date}: {type(exc).__name__}: {exc}")
    return records, success, failure


def main() -> None:
    parser = argparse.ArgumentParser(description="Supplement the map from deterministic public web sources without deleting first-pass data.")
    parser.add_argument("--date", default=datetime.now(TAIPEI).date().isoformat())
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    geojson_path = args.geojson if args.geojson.is_absolute() else PROJECT_DIR / args.geojson
    sources_path = args.sources if args.sources.is_absolute() else PROJECT_DIR / args.sources
    primary_date = date.fromisoformat(args.date).isoformat()

    tracked = control_data.load_tracked_movies()
    movies = control_data.eligible_movies(tracked, date.fromisoformat(primary_date))
    master = control_data.load_cinema_master()
    source_config = load_json(sources_path)
    if source_config.get("schema_version") != 1:
        raise ValueError("supplemental source schema_version must be 1")

    payload = load_json(geojson_path)
    records, success, failure = collect_records(
        primary_date=primary_date,
        movies=movies,
        source_config=source_config,
    )
    payload, features_added, showtimes_added = merge_records_into_geojson(
        payload,
        primary_date=primary_date,
        movies=movies,
        records=records,
        master=master,
    )

    print(
        f"[supplement summary] sources ok/fail={success}/{failure} "
        f"features_added={features_added} showtimes_added={showtimes_added}"
    )
    if args.dry_run:
        print("[supplement] dry-run; GeoJSON not written")
        return
    tmp = geojson_path.with_suffix(geojson_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(geojson_path)
    print(f"[supplement] updated {geojson_path}")


if __name__ == "__main__":
    main()
