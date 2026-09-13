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
from map_availability import sanitize_movie_availability

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_GEOJSON = PROJECT_DIR / "web" / "data" / "locations.geojson"
TAIPEI = ZoneInfo("Asia/Taipei")


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def active_location_ids(master: dict) -> set[int]:
    active_chains = {int(chain["id"]) for chain in master.get("chains", []) if chain.get("active")}
    return {
        int(location["id"])
        for location in master.get("locations", [])
        if location.get("active") and int(location.get("chain_id", -1)) in active_chains
    }


def prune_inactive_or_missing_locations(payload: dict, master: dict) -> tuple[dict, int]:
    allowed = active_location_ids(master)
    by_movie = payload.get("movie_features_by_date")
    if not isinstance(by_movie, dict):
        return payload, 0

    removed = 0
    for title, by_date in list(by_movie.items()):
        if not isinstance(by_date, dict):
            continue
        for show_date, features in list(by_date.items()):
            if not isinstance(features, list):
                continue
            kept = []
            for feature in features:
                props = feature.get("properties") or {}
                location_id = props.get("location_id")
                if location_id is None:
                    kept.append(feature)
                    continue
                try:
                    location_id_int = int(location_id)
                except (TypeError, ValueError):
                    removed += 1
                    continue
                if location_id_int not in allowed:
                    removed += 1
                    continue
                kept.append(feature)
            by_date[show_date] = kept
    return payload, removed


def finalize_payload(payload: dict, master: dict, primary_date: str) -> tuple[dict, int]:
    primary_date = date.fromisoformat(primary_date).isoformat()
    payload, removed = prune_inactive_or_missing_locations(payload, master)
    sanitize_movie_availability(payload, primary_date)
    payload["updated_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    payload["supplemental_finalized_at"] = payload["updated_at"]
    return payload, removed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prune stale supplemental cinema features and re-apply canonical movie availability ordering."
    )
    parser.add_argument("--date", default=datetime.now(TAIPEI).date().isoformat())
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    geojson_path = args.geojson if args.geojson.is_absolute() else PROJECT_DIR / args.geojson
    primary_date = date.fromisoformat(args.date).isoformat()
    payload = load_json(geojson_path)
    master = control_data.load_cinema_master()
    payload, removed = finalize_payload(payload, master, primary_date)

    default_title = payload.get("movie_title")
    default_count = int(payload.get("feature_count") or 0)
    print(
        f"[supplement finalize] removed_stale_features={removed} "
        f"default_movie={default_title!r} default_feature_count={default_count}"
    )
    if args.dry_run:
        print("[supplement finalize] dry-run; GeoJSON not written")
        return

    tmp = geojson_path.with_suffix(geojson_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(geojson_path)
    print(f"[supplement finalize] updated {geojson_path}")


if __name__ == "__main__":
    main()
