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
            """<!doctype html><html><head>
<!-- SEO_MOVIE_LINKS_START -->
<script>window.MuseMoviePageLinks = Object.freeze({});</script>
<!-- SEO_MOVIE_LINKS_END -->
</head><body>
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
                {
                    "id": 3,
                    "title": "第二部動畫",
                    "aliases": ["第二部"],
                    "target_date": "2026-10-01",
                    "poster_url": "assets/posters/second.webp",
                },
            ]
        }
        locations = {
            "updated_at": "2026-10-06T07:24:04+08:00",
            "movie_features_by_date": {
                "測試動畫": {
                    "2026-10-06": [
                        {
                            "geometry": {"type": "Point", "coordinates": [121.5654, 25.0330]},
                            "properties": {
                                "location_id": 101,
                                "chain_name": "威秀影城 / VIESHOW",
                                "location_name": "測試影城 A",
                                "map_name": "測試影城 A",
                                "city": "臺北市",
                                "address": "臺北市測試路 1 號",
                                "location_url": "https://cinema.example/showtimes",
                                "official_url": "https://cinema.example/",
                                "showtime_count": 2,
                                "showtimes": [
                                    {
                                        "time": "13:00",
                                        "format": "IMAX 2D",
                                        "label": "13:00 IMAX 2D",
                                        "language": "日語",
                                        "booking_url": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?txtSessionId=abc",
                                    },
                                    {
                                        "time": "19:30",
                                        "format": "數位",
                                        "label": "19:30 數位",
                                        "language": "日語",
                                    },
                                ],
                            },
                        },
                        {
                            "geometry": {"type": "Point", "coordinates": [120.3014, 22.6273]},
                            "properties": {
                                "location_id": 102,
                                "chain_name": "國賓影城",
                                "location_name": "測試影城 B",
                                "map_name": "測試影城 B",
                                "city": "高雄市",
                                "address": "高雄市測試路 2 號",
                                "location_url": "https://cinema-b.example/showtimes",
                                "official_url": "https://cinema-b.example/",
                                "showtime_count": 1,
                                "showtimes": [
                                    {"time": "21:00", "format": "數位", "label": "21:00 數位"}
                                ],
                            },
                        },
                    ]
                },
                "第二部": {
                    "2026-10-06": [
                        {
                            "geometry": {"type": "Point", "coordinates": [121.46, 25.01]},
                            "properties": {
                                "location_id": 201,
                                "chain_name": "秀泰影城",
                                "location_name": "第二部測試影城",
                                "map_name": "第二部測試影城",
                                "city": "新北市",
                                "address": "新北市測試路 3 號",
                                "showtime_count": 1,
                                "showtimes": [
                                    {"time": "18:20", "format": "數位", "label": "18:20 數位"}
                                ],
                            },
                        }
                    ]
                },
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

    def test_unlabeled_showtime_defaults_to_digital(self) -> None:
        self.assertEqual(
            build_seo_pages.showtime_format_tags(
                {"time": "20:00", "format": "日文(JPN)", "label": "20:00 日文(JPN)"}
            ),
            ["數位"],
        )
        self.assertEqual(
            build_seo_pages.showtime_explicit_format_tags(
                {"time": "20:00", "format": "日文(JPN)", "label": "20:00 日文(JPN)"}
            ),
            [],
        )

    def test_movie_page_keeps_original_map_and_compact_cinema_list(self) -> None:
        result = build_seo_pages.build(
            self.web,
            base_url="https://example.com/anime/",
            today=date(2026, 10, 6),
        )
        self.assertEqual(result["movies"], 3)

        home = (self.web / "index.html").read_text(encoding="utf-8")
        self.assertIn('"測試動畫": "movie-1.html"', home)
        self.assertIn('"第二部": "movie-3.html"', home)

        movie = (self.web / "movie-1.html").read_text(encoding="utf-8")
        self.assertIn("<title>測試動畫電影 場次｜電影場次</title>", movie)
        self.assertIn('class="app-shell movie-detail-shell"', movie)
        self.assertIn('class="sidebar"', movie)
        self.assertIn('id="cinemaListPanel"', movie)
        self.assertIn('class="map-wrap"', movie)
        self.assertIn('id="map"', movie)

        for needle in [
            'id="dateChips"',
            'id="movieSelect"',
            'id="timeSlider"',
            'id="timePeriodButtons"',
            'id="cityFilterList"',
            'id="formatFilterList"',
            'id="chainFilterList"',
            'id="mSeg"',
            'id="mSheet"',
        ]:
            self.assertIn(needle, movie)

        self.assertLess(movie.index('class="sidebar"'), movie.index('id="cinemaListPanel"'))
        self.assertLess(movie.index('id="cinemaListPanel"'), movie.index('class="map-wrap"'))

        self.assertIn('href="styles.css?v=20261007a"', movie)
        self.assertIn('src="app.js?v=20261007c"', movie)
        self.assertIn('src="movie-detail-list.js?v=20261007a"', movie)
        self.assertIn('href="movie-detail-list.css?v=20261007a"', movie)
        self.assertNotIn('id="movieMap"', movie)
        self.assertNotIn('class="movie-workspace"', movie)

        # Crawlable cinema list is intentionally compact: name + showtimes only.
        self.assertIn('<h3 class="cinema-list-name">測試影城 A</h3>', movie)
        self.assertIn('<span class="cinema-list-time">13:00</span>', movie)
        self.assertIn('<span class="cinema-list-time">19:30</span>', movie)
        self.assertIn('<h3 class="cinema-list-name">測試影城 B</h3>', movie)
        self.assertIn('<span class="cinema-list-time">21:00</span>', movie)
        self.assertNotIn("臺北市測試路 1 號", movie)
        self.assertNotIn("前往訂票", movie)
        self.assertNotIn("官方網站", movie)
        self.assertNotIn("更新於 今日 07:24", movie)
        self.assertNotIn("movie-detail-seo-copy", movie)

        # Map app receives canonical movie/date and all movie->page links.
        self.assertIn('"movie": "測試動畫"', movie)
        self.assertIn('"date": "2026-10-06"', movie)
        self.assertIn('"測試動畫": "movie-1.html"', movie)
        self.assertIn('"第二部": "movie-3.html"', movie)

        second = (self.web / "movie-3.html").read_text(encoding="utf-8")
        self.assertIn('id="map"', second)
        self.assertIn('"movie": "第二部"', second)

        upcoming = (self.web / "movie-2.html").read_text(encoding="utf-8")
        self.assertIn("目前沒有可查詢場次", upcoming)
        self.assertNotIn('id="map"', upcoming)

        sitemap = (self.web / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://example.com/anime/movie-1.html", sitemap)
        self.assertIn("https://example.com/anime/movie-3.html", sitemap)


if __name__ == "__main__":
    unittest.main()
