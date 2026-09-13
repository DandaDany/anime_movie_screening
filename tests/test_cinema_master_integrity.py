from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
MASTER_PATH = PROJECT_DIR / "data" / "control" / "cinema_master.json"
ADDRESS_BASE_RE = re.compile(r"^(.*?\d+號)")


def normalize_address_base(value: object) -> str:
    text = str(value or "").strip().replace("臺", "台").replace(" ", "")
    match = ADDRESS_BASE_RE.match(text)
    return match.group(1) if match else text


class CinemaMasterIntegrityTests(unittest.TestCase):
    def test_active_same_chain_locations_do_not_share_same_physical_address(self):
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
