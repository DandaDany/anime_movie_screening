from __future__ import annotations

import json
import re
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
<!-- SEO_TODAY_AI_START -->
<script id="todayShowtimesStructuredData" type="application/ld+json">{"@context":"https://schema.org","@graph":[]}</script>
<!-- SEO_TODAY_AI_END -->
<!-- SEO_HOME_META_START -->
<footer class="movie-discovery__meta"><p>placeholder</p></footer>
<!-- SEO_HOME_META_END -->
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

        control_dir = Path(self.temp_dir.name) / "data" / "control"
        control_dir.mkdir(parents=True)
        tracked = {
            "schema_version": 1,
            "movies": [
                {
                    "id": 4,
                    "title": "已下檔動畫電影",
                    "aliases": [],
                    "target_date": "2026-08-01",
                    "is_active": False,
                },
                {
                    "id": 5,
                    "title": "停用未上映草稿",
                    "aliases": [],
                    "target_date": "2026-12-01",
                    "is_active": False,
                },
            ],
        }
        (control_dir / "tracked_movies.json").write_text(
            json.dumps(tracked, ensure_ascii=False), encoding="utf-8"
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
        self.assertEqual(result["movies"], 4)

        home = (self.web / "index.html").read_text(encoding="utf-8")
        self.assertIn('"測試動畫": "movie-1.html"', home)
        self.assertIn('"第二部": "movie-3.html"', home)
        self.assertIn(
            '<time datetime="2026-10-06T07:24:04+08:00">今日 07:24</time>',
            home,
        )
        self.assertIn(
            "場次資訊持續更新中｜實際上映與售票狀況請以影城官方資訊為準。",
            home,
        )
        self.assertIn('<a href="about.html">資料來源與更新方式</a>', home)

        today_match = re.search(
            r'<script id="todayShowtimesStructuredData" type="application/ld\+json">(.*?)</script>',
            home,
            flags=re.S,
        )
        self.assertIsNotNone(today_match)
        today_structured = json.loads(today_match.group(1))
        today_graph = today_structured["@graph"]
        today_by_type = {}
        for node in today_graph:
            today_by_type.setdefault(node.get("@type"), []).append(node)

        today_page = today_by_type["WebPage"][0]
        self.assertEqual(today_page["dateModified"], "2026-10-06T07:24:04+08:00")
        today_list = today_by_type["ItemList"][0]
        self.assertEqual(today_list["name"], "2026/10/06 今天可看的動畫電影")
        self.assertEqual(today_list["numberOfItems"], 2)
        today_movies = [entry["item"] for entry in today_list["itemListElement"]]
        self.assertEqual(
            {movie["name"] for movie in today_movies},
            {"測試動畫電影", "第二部動畫"},
        )
        first_summary = next(
            movie["subjectOf"] for movie in today_movies
            if movie["name"] == "測試動畫電影"
        )
        self.assertEqual(first_summary["temporalCoverage"], "2026-10-06")
        self.assertEqual(
            [place["name"] for place in first_summary["spatialCoverage"]],
            ["臺北市", "高雄市"],
        )
        summary_values = {
            value["name"]: value["value"]
            for value in first_summary["variableMeasured"]
        }
        self.assertEqual(summary_values["今日場次數"], 3)
        self.assertEqual(summary_values["上映影城數"], 2)
        self.assertEqual(summary_values["最早場次"], "13:00")
        self.assertEqual(summary_values["最晚場次"], "21:00")
        self.assertEqual(summary_values["上映版本"], "IMAX、數位、2D")
        self.assertNotIn("未來動畫電影", json.dumps(today_structured, ensure_ascii=False))

        movie = (self.web / "movie-1.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="index, follow, max-image-preview:large" />', movie)
        self.assertIn("<title>測試動畫電影 場次｜電影場次</title>", movie)
        self.assertIn('<section class="seo-visually-hidden" aria-label="測試動畫電影 場次頁面資訊">', movie)
        self.assertIn("<h1>測試動畫電影 場次</h1>", movie)
        self.assertIn('<time datetime="2026-10-01">2026/10/01</time>', movie)
        self.assertIn('<h2 class="seo-visually-hidden"><time datetime="2026-10-06">2026/10/06</time> 場次</h2>', movie)
        self.assertIn('<p class="panel-title">電影場次</p>', movie)

        jsonld_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            movie,
            flags=re.S,
        )
        self.assertIsNotNone(jsonld_match)
        structured = json.loads(jsonld_match.group(1))
        graph = structured["@graph"]
        by_type = {}
        for node in graph:
            by_type.setdefault(node.get("@type"), []).append(node)

        webpage = by_type["WebPage"][0]
        self.assertEqual(webpage["dateModified"], "2026-10-06T07:24:04+08:00")
        self.assertEqual(webpage["publisher"]["@id"], "https://example.com/anime/#publisher")
        self.assertIn("https://cinema.example/", webpage["citation"])
        self.assertIn("https://cinema-b.example/", webpage["citation"])
        self.assertEqual(by_type["Organization"][0]["name"], "電影場次")
        self.assertEqual(
            by_type["Organization"][0]["logo"]["url"],
            "https://example.com/anime/assets/brand/logo-transparent.png",
        )
        self.assertEqual(by_type["Movie"][0]["name"], "測試動畫電影")
        self.assertEqual(len(by_type["MovieTheater"]), 2)
        self.assertEqual(
            {city["name"] for city in by_type["City"]},
            {"臺北市", "高雄市"},
        )
        self.assertEqual(len(webpage["spatialCoverage"]), 2)
        city_ids = {city["@id"] for city in by_type["City"]}
        self.assertTrue(
            all(
                theater["containedInPlace"]["@id"] in city_ids
                for theater in by_type["MovieTheater"]
            )
        )

        screening = next(
            node for node in by_type["ScreeningEvent"]
            if node["startDate"] == "2026-10-06T13:00:00+08:00"
        )
        self.assertEqual(screening["workPresented"]["@id"], "https://example.com/anime/movie-1.html#movie")
        self.assertEqual(
            screening["offers"]["url"],
            "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?txtSessionId=abc",
        )
        self.assertEqual(
            [value["name"] for value in screening["about"]],
            ["IMAX", "2D"],
        )
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
        self.assertIn('src="movie-detail-list.js?v=20261008a"', movie)
        self.assertIn('href="movie-detail-list.css?v=20261008b"', movie)
        self.assertIn(
            'rel="icon" type="image/png" sizes="48x48" href="assets/brand/favicon-48.png"',
            movie,
        )
        self.assertIn('rel="apple-touch-icon" sizes="180x180" href="assets/brand/apple-touch-icon.png"', movie)
        self.assertNotIn('id="movieMap"', movie)
        self.assertNotIn('class="movie-workspace"', movie)

        # Crawlable cinema list is intentionally compact: name + showtimes only.
        self.assertIn('<h3 class="cinema-list-name">測試影城 A</h3>', movie)
        self.assertIn('<span class="cinema-list-city-tag">臺北市</span>', movie)
        self.assertIn('<span class="cinema-list-city-tag">高雄市</span>', movie)
        self.assertNotIn('id="cinemaListCount"', movie)
        self.assertIn(
            '<time class="cinema-list-time" datetime="2026-10-06T13:00:00+08:00" '
            'data-formats="IMAX|2D" '
            'data-booking-url="https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?txtSessionId=abc">13:00</time>',
            movie,
        )
        self.assertIn(
            '<time class="cinema-list-time" datetime="2026-10-06T19:30:00+08:00" '
            'data-formats="數位">19:30</time>',
            movie,
        )
        self.assertIn('<h3 class="cinema-list-name">測試影城 B</h3>', movie)
        self.assertIn(
            '<section class="cinema-list-city" data-seo-city="臺北市">'
            '<h3 class="seo-visually-hidden">臺北市</h3>',
            movie,
        )
        self.assertIn(
            '<section class="cinema-list-city" data-seo-city="高雄市">'
            '<h3 class="seo-visually-hidden">高雄市</h3>',
            movie,
        )
        self.assertIn(
            '<time class="cinema-list-time" datetime="2026-10-06T21:00:00+08:00" '
            'data-formats="數位">21:00</time>',
            movie,
        )
        visible_list = movie[
            movie.index('<section class="cinema-list-panel"'):
            movie.index('<section class="map-wrap"')
        ]
        self.assertNotIn("臺北市測試路 1 號", visible_list)
        self.assertNotIn("前往訂票", visible_list)
        self.assertNotIn("官方網站", visible_list)
        self.assertNotIn("更新於 今日 07:24", visible_list)
        self.assertNotIn("movie-detail-seo-copy", visible_list)

        # Address/source details are intentionally machine-readable in JSON-LD,
        # not added to the compact visible list.
        self.assertEqual(
            by_type["MovieTheater"][0]["address"]["streetAddress"],
            "臺北市測試路 1 號",
        )

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
        self.assertIn("background:linear-gradient(90deg,rgba(10,11,15,.96)", upcoming)
        self.assertIn("color:#fff", upcoming)
        self.assertNotIn('id="map"', upcoming)

        archive = (self.web / "movie-4.html").read_text(encoding="utf-8")
        self.assertIn("<title>已下檔動畫電影｜已無上映場次｜電影場次</title>", archive)
        self.assertIn("<h1", archive)
        self.assertIn("已下檔動畫電影 場次", archive)
        self.assertIn("目前已無上映場次", archive)
        self.assertIn('<time datetime="2026-08-01">', archive)
        self.assertNotIn('id="map"', archive)
        self.assertFalse((self.web / "movie-5.html").exists())

        # Archive pages remain indexable but are not reintroduced into the active homepage.
        self.assertNotIn("已下檔動畫電影", home)

        sitemap = (self.web / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://example.com/anime/about.html", sitemap)
        self.assertIn("https://example.com/anime/movie-1.html", sitemap)
        self.assertIn("https://example.com/anime/movie-3.html", sitemap)
        self.assertIn("https://example.com/anime/movie-4.html", sitemap)
        self.assertNotIn("https://example.com/anime/movie-5.html", sitemap)

        robots = (self.web / "robots.txt").read_text(encoding="utf-8")
        for agent in ("OAI-SearchBot", "PerplexityBot", "Googlebot", "Bingbot"):
            self.assertIn(f"User-agent: {agent}\nAllow: /", robots)
        self.assertIn("User-agent: *\nAllow: /", robots)
        self.assertIn("Sitemap: https://example.com/anime/sitemap.xml", robots)


if __name__ == "__main__":
    unittest.main()
