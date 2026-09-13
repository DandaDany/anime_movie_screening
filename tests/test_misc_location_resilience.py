from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_misc_locations as misc  # noqa: E402


class MiscLocationResilienceTests(unittest.TestCase):
    def test_miranew_failure_returns_degraded_state_instead_of_raising(self) -> None:
        with patch.object(misc, "fetch_text", side_effect=RuntimeError("source unavailable")):
            locations, error = misc.load_miranew_locations(None)

        self.assertEqual(locations, [])
        self.assertIsNotNone(error)
        self.assertIn("source unavailable", error or "")

    def test_fixed_locations_still_save_without_miranew(self) -> None:
        expected_fixed = sum(len(group["locations"]) for group in misc.FIXED_CHAIN_LOCATIONS)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "movie_map.sqlite"
            saved = misc.save_locations([], db_path, "2026-09-13")

        self.assertEqual(saved, expected_fixed)
        self.assertGreater(expected_fixed, 0)


if __name__ == "__main__":
    unittest.main()
