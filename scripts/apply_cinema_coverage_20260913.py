from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import control_data

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = PROJECT_DIR / "data" / "input" / "cinema_coverage_20260913.json"
TAIPEI = ZoneInfo("Asia/Taipei")


def load_plan(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("coverage plan schema_version must be 1")
    if not isinstance(payload.get("chains"), list) or not isinstance(payload.get("locations"), list):
        raise ValueError("coverage plan chains/locations must be lists")
    if not isinstance(payload.get("patch_locations", []), list):
        raise ValueError("coverage plan patch_locations must be a list")
    return payload


def upsert_by_id(records: list[dict], incoming: dict, *, name_field: str) -> str:
    by_id = {record["id"]: record for record in records}
    current = by_id.get(incoming["id"])
    collision = next(
        (
            record
            for record in records
            if record.get(name_field) == incoming.get(name_field) and record.get("id") != incoming.get("id")
        ),
        None,
    )
    if collision is not None:
        raise ValueError(
            f"{name_field} collision: {incoming[name_field]!r} already uses id={collision['id']}"
        )
    if current is None:
        records.append(dict(incoming))
        return "added"
    if current == incoming:
        return "unchanged"
    # Canonical-name corrections are permitted only when the stable ID is unchanged and
    # the new name is not owned by another record.  ID collisions still fail closed.
    current.clear()
    current.update(incoming)
    return "updated"


def apply_plan(master: dict, plan: dict) -> dict[str, int]:
    counters = {"chains_added": 0, "chains_updated": 0, "locations_added": 0, "locations_updated": 0, "patches": 0}

    for chain in plan["chains"]:
        status = upsert_by_id(master["chains"], chain, name_field="chain_name")
        if status == "added": counters["chains_added"] += 1
        elif status == "updated": counters["chains_updated"] += 1

    for location in plan["locations"]:
        status = upsert_by_id(master["locations"], location, name_field="location_name")
        if status == "added": counters["locations_added"] += 1
        elif status == "updated": counters["locations_updated"] += 1

    location_by_id = {location["id"]: location for location in master["locations"]}
    for patch in plan.get("patch_locations", []):
        target = location_by_id.get(patch.get("id"))
        if target is None:
            raise ValueError(f"patch references missing location id={patch.get('id')}")
        changed = False
        for key, value in patch.items():
            if key == "id": continue
            if target.get(key) != value:
                target[key] = value
                changed = True
        if changed: counters["patches"] += 1

    master["chains"].sort(key=lambda item: item["id"])
    master["locations"].sort(key=lambda item: item["id"])
    master["generated_at"] = datetime.now(TAIPEI).isoformat(timespec="seconds")
    control_data.validate_cinema_master(master)
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the verified 2026-09-13 Taiwan cinema coverage expansion.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--master", type=Path, default=control_data.CINEMA_MASTER_PATH)
    parser.add_argument("--check", action="store_true", help="Validate/apply in memory without writing.")
    args = parser.parse_args()

    plan_path = args.plan if args.plan.is_absolute() else PROJECT_DIR / args.plan
    master_path = args.master if args.master.is_absolute() else PROJECT_DIR / args.master
    plan = load_plan(plan_path)
    master = control_data.load_cinema_master(master_path)
    counters = apply_plan(master, plan)
    if not args.check:
        control_data._atomic_json_write(master_path, master)

    active = control_data.active_cinema_payload(master)
    print(
        "[cinema coverage] "
        f"chains +{counters['chains_added']} updated={counters['chains_updated']}; "
        f"locations +{counters['locations_added']} updated={counters['locations_updated']}; "
        f"patches={counters['patches']}; "
        f"active_chains={active['chain_count']} active_locations={active['location_count']}"
    )
    if args.check:
        print("[cinema coverage] check-only; master file not written")


if __name__ == "__main__":
    main()
