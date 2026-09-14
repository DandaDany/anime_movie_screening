from __future__ import annotations

import unittest

from scripts.apply_web_research_supplement import normalize_research_records


class WebResearchSupplementValidationTests(unittest.TestCase):
    def setUp(self):
        self.master = {
            "locations": [
                {"id": 104, "active": True},
                {"id": 115, "active": True},
                {"id": 999, "active": False},
            ]
        }
        self.movies = [{"title": "劇場版 吉伊卡哇 人魚島的秘密", "aliases": []}]

    def valid_payload(self):
        return {
            "schema_version": 1,
            "for_date": "2026-09-13",
            "generated_at": "2026-09-13T06:00:00+08:00",
            "records": [
                {
                    "location_id": 104,
                    "movie_title": "劇場版 吉伊卡哇 人魚島的秘密",
                    "show_date": "2026-09-13",
                    "source_url": "https://example.com/post",
                    "evidence": "麻豆戲院 9/13 明列吉伊卡哇 19:00",
                    "showtimes": [{"time": "19:00", "language": "日語"}],
                }
            ],
        }

    def test_accepts_explicit_verified_record(self):
        for_date, records = normalize_research_records(
            self.valid_payload(), master=self.master, movies=self.movies
        )
        self.assertEqual(for_date, "2026-09-13")
        self.assertIn(("劇場版 吉伊卡哇 人魚島的秘密", "2026-09-13", 104), records)

    def test_rejects_untracked_movie(self):
        payload = self.valid_payload()
        payload["records"][0]["movie_title"] = "不是追蹤中的電影"
        with self.assertRaises(ValueError):
            normalize_research_records(payload, master=self.master, movies=self.movies)

    def test_rejects_inactive_or_unknown_location(self):
        payload = self.valid_payload()
        payload["records"][0]["location_id"] = 999
        with self.assertRaises(ValueError):
            normalize_research_records(payload, master=self.master, movies=self.movies)

    def test_rejects_missing_evidence(self):
        payload = self.valid_payload()
        payload["records"][0]["evidence"] = ""
        with self.assertRaises(ValueError):
            normalize_research_records(payload, master=self.master, movies=self.movies)

    def test_rejects_date_outside_supported_window(self):
        payload = self.valid_payload()
        payload["records"][0]["show_date"] = "2026-10-01"
        with self.assertRaises(ValueError):
            normalize_research_records(payload, master=self.master, movies=self.movies)

    def test_rejects_invalid_time(self):
        payload = self.valid_payload()
        payload["records"][0]["showtimes"][0]["time"] = "25:90"
        with self.assertRaises(ValueError):
            normalize_research_records(payload, master=self.master, movies=self.movies)


if __name__ == "__main__":
    unittest.main()
