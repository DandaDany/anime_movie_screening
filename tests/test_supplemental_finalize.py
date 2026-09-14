from __future__ import annotations

import unittest

from scripts.finalize_supplemental_geojson import finalize_payload


class SupplementalFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.master = {
            "chains": [{"id": 1, "active": True}],
            "locations": [
                {"id": 1, "chain_id": 1, "active": True},
                {"id": 2, "chain_id": 1, "active": True},
            ],
        }

    @staticmethod
    def feature(location_id: int, movie_title: str, show_date: str, time: str) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [121.0, 25.0]},
            "properties": {
                "location_id": location_id,
                "movie_title": movie_title,
                "show_date": show_date,
                "showtime_count": 1,
                "showtimes": [{"time": time}],
                "start_times": time,
            },
        }

    def test_prunes_missing_location_and_prioritizes_movie_with_today_showtimes(self):
        future_title = "未來才有場次"
        today_title = "今天有場次"
        payload = {
            "movies": [
                {"title": future_title},
                {"title": today_title},
            ],
            "movie_features_by_date": {
                future_title: {
                    "2026-09-15": [self.feature(1, future_title, "2026-09-15", "10:00")],
                },
                today_title: {
                    "2026-09-14": [
                        self.feature(2, today_title, "2026-09-14", "12:00"),
                        self.feature(116, today_title, "2026-09-14", "14:00"),
                    ],
                },
            },
        }

        finalized, removed = finalize_payload(payload, self.master, "2026-09-14")

        self.assertEqual(removed, 1)
        self.assertEqual(finalized["movie_title"], today_title)
        self.assertEqual(finalized["feature_count"], 1)
        self.assertEqual(finalized["features"][0]["properties"]["location_id"], 2)
        self.assertEqual([item["title"] for item in finalized["movies"]], [today_title, future_title])
        all_location_ids = {
            feature["properties"]["location_id"]
            for by_date in finalized["movie_features_by_date"].values()
            for features in by_date.values()
            for feature in features
        }
        self.assertNotIn(116, all_location_ids)


if __name__ == "__main__":
    unittest.main()
