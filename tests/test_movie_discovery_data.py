import json
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import build_movie_discovery_data as discovery

ROOT = Path(__file__).resolve().parents[1]
TRACKED = ROOT / "data" / "control" / "tracked_movies.json"
POSTERS = ROOT / "web" / "data" / "movie_posters.json"
DISCOVERY = ROOT / "web" / "data" / "movie_discovery.json"


class MovieDiscoveryDataTests(unittest.TestCase):
    def setUp(self):
        self.tracked = json.loads(TRACKED.read_text(encoding="utf-8"))
        self.posters = json.loads(POSTERS.read_text(encoding="utf-8"))

    def _poster_for(self, movie):
        index = discovery._poster_index(self.posters)
        return discovery._find_poster(movie, index)

    def test_every_canonical_movie_has_https_poster(self):
        self.assertGreater(len(self.tracked["movies"]), 0)
        self.assertEqual(len(self.tracked["movies"]), self.posters["movie_count"])
        for movie in self.tracked["movies"]:
            with self.subTest(movie=movie["title"]):
                poster = self._poster_for(movie)
                self.assertIsNotNone(poster)
                poster_url = str(poster.get("poster_url") or "")\n                self.assertTrue(\n                    poster_url.startswith("https://") or poster_url.startswith("assets/posters/")\n                )
                fallback_url = str(poster.get("poster_fallback_url") or "")
                self.assertTrue(not fallback_url or fallback_url.startswith("https://"))
                self.assertNotEqual(fallback_url, str(poster.get("poster_url") or ""))
                self.assertTrue(str(poster.get("poster_source") or "").strip())

    def test_upcoming_posters_have_traceable_sources(self):
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        poster_by_title = {item["title"]: item for item in self.posters["movies"]}

        for movie in self.tracked["movies"]:
            if not movie.get("is_active") or str(movie.get("target_date") or "") <= today:
                continue
            poster = poster_by_title[movie["title"]]
            poster_url = str(poster.get("poster_url") or "")
            source = str(poster.get("poster_source") or "")
            source_url = str(poster.get("poster_source_url") or "")
            with self.subTest(movie=movie["title"]):
                self.assertTrue(poster_url.startswith("https://"))
                self.assertTrue(source.strip())
                self.assertTrue(source_url.startswith("https://"))
                # Image correctness is the primary requirement. URL host,
                # source format and aspect ratio do not invalidate a known-good
                # image; the browser runtime acceptance verifies that it loads.
                if "UPCOMING FALLBACK" in source:
                    self.assertEqual(source, "日本官方 Poster（UPCOMING FALLBACK）")

    def test_poster_fit_modes_are_valid(self):
        allowed = {None, "cover", "contain"}
        for poster in self.posters["movies"]:
            with self.subTest(movie=poster["title"]):
                self.assertIn(poster.get("poster_fit"), allowed)

    def test_japan_poster_fallback_is_upcoming_only(self):
        today = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
        tracked_by_title = {item["title"]: item for item in self.tracked["movies"]}
        for poster in self.posters["movies"]:
            source = str(poster.get("poster_source") or "")
            if "UPCOMING FALLBACK" not in source:
                continue
            movie = tracked_by_title[poster["title"]]
            with self.subTest(movie=movie["title"]):
                self.assertTrue(movie.get("is_active"))
                self.assertGreater(
                    str(movie.get("target_date") or ""),
                    today,
                    "Japanese poster fallback is only allowed before the Taiwan release date",
                )

    def test_generated_feed_uses_canonical_active_movies_and_dates(self):
        payload = discovery.build_payload(self.tracked, self.posters)
        expected = [movie for movie in self.tracked["movies"] if movie["is_active"]]
        self.assertEqual(payload["count"], len(expected))
        self.assertEqual(payload["missing_poster_count"], 0)
        self.assertEqual(payload["missing_posters"], [])

        actual_by_id = {movie["id"]: movie for movie in payload["movies"]}
        self.assertEqual(set(actual_by_id), {movie["id"] for movie in expected})
        for movie in expected:
            with self.subTest(movie=movie["title"]):
                actual = actual_by_id[movie["id"]]
                self.assertEqual(actual["title"], movie["title"])
                self.assertEqual(actual["target_date"], movie["target_date"])
                self.assertTrue(actual["poster_url"].startswith("https://"))
                self.assertEqual(
                    actual.get("poster_fallback_url"),
                    self._poster_for(movie).get("poster_fallback_url"),
                )

    def test_committed_feed_matches_builder(self):
        expected = discovery.build_payload(self.tracked, self.posters)
        actual = json.loads(DISCOVERY.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
