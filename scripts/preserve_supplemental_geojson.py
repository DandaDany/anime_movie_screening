from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import control_data
from supplemental_web_update import merge_feature, merge_records_into_geojson

PROJECT_DIR = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def preserve_supplemental_features(target: dict, previous: dict, primary_date: str) -> tuple[dict, int, int]:
    target_by_date = target.setdefault("movie_features_by_date", {})
    kept_features = 0
    kept_showtimes = 0

    for movie_title, previous_dates in (previous.get("movie_features_by_date") or {}).items():
        for show_date, features in (previous_dates or {}).items():
            if show_date < primary_date:
                continue
            for feature in features or []:
                props = feature.get("properties") or {}
                if not props.get("supplemental_web_source") or int(props.get("showtime_count") or 0) <= 0:
                    continue
                day_features = list(target_by_date.setdefault(movie_title, {}).get(show_date) or [])
                location_id = props.get("location_id")
                index = next(
                    (
                        idx for idx, candidate in enumerate(day_features)
                        if (candidate.get("properties") or {}).get("location_id") == location_id
                    ),
                    None,
                )
                if index is None:
                    day_features.append(feature)
                    kept_features += 1
                    kept_showtimes += int(props.get("showtime_count") or 0)
                else:
                    merged, added = merge_feature(day_features[index], feature)
                    day_features[index] = merged
                    kept_showtimes += added
                day_features.sort(key=lambda item: str((item.get("properties") or {}).get("map_name") or ""))
                target_by_date[movie_title][show_date] = day_features

    return target, kept_features, kept_showtimes


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore verified 06:00 supplemental features after a full crawler export.")
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=PROJECT_DIR / "web" / "data" / "locations.geojson")
    parser.add_argument("--date", default=datetime.now(TAIPEI).date().isoformat())
    args = parser.parse_args()

    source = args.source if args.source.is_absolute() else PROJECT_DIR / args.source
    target_path = args.target if args.target.is_absolute() else PROJECT_DIR / args.target
    primary_date = date.fromisoformat(args.date).isoformat()
    previous = load(source)
    target = load(target_path)
    target, features, showtimes = preserve_supplemental_features(target, previous, primary_date)

    tracked = control_data.load_tracked_movies()
    movies = control_data.eligible_movies(tracked, date.fromisoformat(primary_date))
    master = control_data.load_cinema_master()
    target, _, _ = merge_records_into_geojson(
        target,
        primary_date=primary_date,
        movies=movies,
        records={},
        master=master,
    )
    target["supplemental_preserved_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    tmp = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target_path)
    print(f"[preserve supplement] features={features} showtimes={showtimes} from={source}")


if __name__ == "__main__":
    main()
