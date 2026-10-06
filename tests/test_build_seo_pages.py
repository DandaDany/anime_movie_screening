from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import build_seo_pages


class BuildSeoPagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.web = Path(self.temp_dir.name) / "web"
        (self.web / "data").mkdir(parents=True)
        (self.web / "index.html").write_text(
            """<!doctype html><html><body>
<!-- SEO_PRERENDER_NOW_START -->
<div class="movie-grid" id="nowShowingGrid"></div>
<!-- SEO_PRERENDER_NOW_END -->
<!-- SEO_PRERENDER_UPCOMING_START -->
<div class="movie-grid" id="comingSoonGrid"></div>
<!-- SEO_PRERENDER_UPCOMING_END -->
</body></html>""",
            encoding="utf-8",
        )
        discovery = {
            "movies": [
                {
                    "id": 1,
                    "title": "測試動畫電影",
                    "aliases": ["測試動畫"],
                    "target_date": "2026-10-01",
                    "poster_url": "assets/posters/test.webp",
                },
                {
                    "id": 2,
                    "title": "未來動畫電影",
                    "aliases": [],
                    "target_date": "2026-10-20",
                    "poster_url": "https://example.com/upcoming.jpg",
                },
            ]
        }
        locations = {
            "updated_at": "2026-10-06T07:00:00+08:00",
            "movie_features_by_date": {
                "測試動畫": {
                    "2026-10-06": [
                        {
                            "properties": {
                                "city": "臺北市",
                                "map_name": "測試影城",
                                "address": "臺北市測試路 1 號",
                                "location_url": "https://cinema.example/",
                                "showtime_count": 2,
                                "showtimes": [
                                    {"time": "13:00", "format": "2D", "language": "日語"},
                                    {"time": "19:30", "format": "2D", "language": "日語"},
                                ],
                            }
                        }
                    ]
                }
            },
        }
        (self.web / "data" / "movie_discovery.json").write_text(
            json.dumps(discovery, ensure_ascii=False), encoding="utf-8"
        )
        (self.web / "data" / "locations.geojson").write_text(
            json.dumps(locations, ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builds_crawlable_home_movie_pages_sitemap_and_robots(self) -> None:
        result = build_seo_pages.build(
            self.web,
            base_url="https://example.com/anime/",
            today=date(2026, 10, 6),
        )

        self.assertEqual(result["movies"], 2)
        home = (self.web / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="movies/1/"', home)
        self.assertIn("測試動畫電影", home)
        self.assertIn('href="movies/2/"', home)
        self.assertIn("未來動畫電影", home)

        movie = (self.web / "movies" / "1" / "index.html").read_text(encoding="utf-8")
        self.assertIn("測試動畫電影 場次｜全台動畫電影上映地圖", movie)
        self.assertIn("測試影城", movie)
        self.assertIn("13:00", movie)
        self.assertIn("19:30", movie)
        self.assertIn('<link rel="canonical" href="https://example.com/anime/movies/1/"', movie)
        self.assertIn('"@type": "Movie"', movie)

        upcoming = (self.web / "movies" / "2" / "index.html").read_text(encoding="utf-8")
        self.assertIn("目前沒有可查詢場次", upcoming)

        sitemap = (self.web / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://example.com/anime/", sitemap)
        self.assertIn("https://example.com/anime/movies/1/", sitemap)
        self.assertIn("https://example.com/anime/movies/2/", sitemap)

        robots = (self.web / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("Allow: /", robots)
        self.assertIn("https://example.com/anime/sitemap.xml", robots)


if __name__ == "__main__":
    unittest.main()
