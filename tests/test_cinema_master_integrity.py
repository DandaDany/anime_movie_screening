from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
MASTER_PATH = PROJECT_DIR / "data" / "control" / "cinema_master.json"
ADDRESS_BASE_RE = re.compile(r"^(.*?\d+號)")
SPECIAL_HALL_RE = re.compile(r"\((?:GC|MUCROWN)\)", re.IGNORECASE)


def normalize_address_base(value: object) -> str:
    text = str(value or "").strip().replace("臺", "台").replace(" ", "")
    match = ADDRESS_BASE_RE.match(text)
    return match.group(1) if match else text


def intentional_special_hall_split(first: dict, second: dict) -> bool:
    """Allow the project's existing same-pin special-auditorium records.

    VIESHOW/MUVIE intentionally models GC/MUCROWN as separate source records when
    they have the exact same physical coordinates as the base cinema. This is not
    the same failure mode as accidentally creating a second physical cinema row.
    """
    same_coordinates = (
        first.get("latitude") == second.get("latitude")
        and first.get("longitude") == second.get("longitude")
    )
    names = f"{first.get('location_name', '')} {second.get('location_name', '')}"
    return same_coordinates and bool(SPECIAL_HALL_RE.search(names))


class CinemaMasterIntegrityTests(unittest.TestCase):
    def test_active_same_chain_locations_do_not_duplicate_physical_cinema(self):
        payload = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        seen: dict[tuple[int, str], dict] = {}
        duplicates: list[tuple[dict, dict]] = []

        for location in payload.get("locations", []):
            if not location.get("active"):
                continue
            key = (int(location["chain_id"]), normalize_address_base(location.get("address")))
            if not key[1]:
                continue
            previous = seen.get(key)
            if previous is not None:
                if intentional_special_hall_split(previous, location):
                    continue
                duplicates.append((previous, location))
            else:
                seen[key] = location

        self.assertEqual(
            duplicates,
            [],
            msg="duplicate active physical cinema locations detected: "
            + "; ".join(
                f"id={a['id']} {a['location_name']} <-> id={b['id']} {b['location_name']}"
                for a, b in duplicates
            ),
        )

    def test_location_ids_are_unique(self):
        payload = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        ids = [int(location["id"]) for location in payload.get("locations", [])]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
