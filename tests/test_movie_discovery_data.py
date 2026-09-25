import json
import unittest
from pathlib import Path

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
                self.assertTrue(str(poster.get("poster_url") or "").startswith("https://"))
                self.assertTrue(str(poster.get("poster_source") or "").strip())

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

    def test_committed_feed_matches_builder(self):
        expected = discovery.build_payload(self.tracked, self.posters)
        actual = json.loads(DISCOVERY.read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
