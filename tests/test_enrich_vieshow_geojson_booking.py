from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import enrich_vieshow_geojson_booking as enrich  # noqa: E402


class EnrichVieshowGeojsonBookingTests(unittest.TestCase):
    def test_collects_multimovie_feature_with_title_hint(self) -> None:
        feature = {
            "type": "Feature",
            "properties": {
                "location_id": 1,
                "chain_name": "威秀影城 / VIESHOW",
                "showtimes": [{"time": "19:00"}],
            },
            "geometry": {"type": "Point", "coordinates": [121.5, 25.0]},
        }
        payload = {
            "movie_features_by_date": {
                "測試電影": {"2026-09-26": [feature]}
            },
            "features": [],
        }
        refs = enrich.collect_feature_refs(payload)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0][1], "測試電影")

    def test_exact_date_time_returns_direct_url(self) -> None:
        showtime = {
            "time": "19:25",
            "show_date": "2026-09-26",
            "format": "(IMAX)測試電影",
        }
        candidates = [
            {
                "show_date": "2026-09-26",
                "start_time": "19:25",
                "movie_text": "(IMAX)測試電影",
                "booking_url": "https://example.test/direct",
            }
        ]
        self.assertEqual(
            enrich.choose_booking_url(showtime, candidates),
            "https://example.test/direct",
        )

    def test_ambiguous_same_time_without_format_match_is_not_guessed(self) -> None:
        showtime = {
            "time": "19:25",
            "show_date": "2026-09-26",
            "format": "測試電影",
        }
        candidates = [
            {
                "show_date": "2026-09-26",
                "start_time": "19:25",
                "movie_text": "(IMAX)測試電影",
                "booking_url": "https://example.test/imax",
            },
            {
                "show_date": "2026-09-26",
                "start_time": "19:25",
                "movie_text": "(4DX)測試電影",
                "booking_url": "https://example.test/4dx",
            },
        ]
        self.assertIsNone(enrich.choose_booking_url(showtime, candidates))


if __name__ == "__main__":
    unittest.main()
