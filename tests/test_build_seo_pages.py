from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
            "updated_at": "2026-10-06T07:24:04+08:00",
            "movie_features_by_date": {
                "測試動畫": {
                    "2026-10-06": [
                        {
                            "geometry": {"type": "Point", "coordinates": [121.5654, 25.0330]},
                            "properties": {
                                "city": "臺北市",
                                "map_name": "測試影城 A",
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
                                    {
                                        "time": "20:10",
                                        "format": "01廳(9F)",
                                        "label": "20:10 01廳(9F)",
                                        "language": "日語",
                                    },
                                    {
                                        "time": "20:20",
                                        "format": "日文(JPN)",
                                        "label": "20:20 日文(JPN)",
                                        "language": "日語",
                                    },
                                    {
                                        "time": "20:30",
                                        "format": "(日文版)劇場版 吉伊卡哇 人魚島的秘密",
                                        "label": "20:30 (日文版)劇場版 吉伊卡哇 人魚島的秘密",
                                        "language": "日語",
                                    },
                                ],
                            },
                        },
                        {
                            "geometry": {"type": "Point", "coordinates": [120.3014, 22.6273]},
                            "properties": {
                                "city": "高雄市",
                                "map_name": "測試影城 B",
                                "address": "高雄市測試路 2 號",
                                "location_url": "https://cinema-b.example/showtimes",
                                "official_url": "https://cinema-b.example/",
                                "showtime_count": 1,
                                "showtimes": [
                                    {
                                        "time": "21:00",
                                        "format": "數位",
                                        "label": "21:00 數位",
                                        "language": "日語",
                                    }
                                ],
                            },
                        },
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

    def test_builds_movie_detail_with_correct_map_state_filters_and_actions(self) -> None:
        result = build_seo_pages.build(
            self.web,
            base_url="https://example.com/anime/",
            today=date(2026, 10, 6),
        )

        self.assertEqual(result["movies"], 2)
        home = (self.web / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="movie-1.html"', home)
        self.assertIn('href="movie-2.html"', home)

        movie = (self.web / "movie-1.html").read_text(encoding="utf-8")
        self.assertIn("測試動畫電影 場次｜全台動畫電影上映地圖", movie)
        self.assertIn("場次資料更新：<strong>今日 07:24</strong>", movie)
        self.assertNotIn("2026-10-06T07:24:04+08:00", movie)

        self.assertIn('id="movieFilterCity"', movie)
        self.assertIn('id="movieFilterFormat"', movie)
        self.assertIn('id="movieFilterTime"', movie)
        self.assertIn(">臺北市</option>", movie)
        self.assertIn(">高雄市</option>", movie)
        self.assertIn(">IMAX</option>", movie)
        self.assertIn(">數位</option>", movie)
        self.assertNotIn(">01廳(9F)</option>", movie)
        self.assertNotIn(">日文(JPN)</option>", movie)
        self.assertNotIn(">(日文版)劇場版 吉伊卡哇 人魚島的秘密</option>", movie)
        self.assertNotIn("全台動畫電影場次", movie)

        self.assertIn('data-lat="25.033"', movie)
        self.assertIn('data-long="121.5654"', movie)
        self.assertIn("seo-movie.js", movie)

        self.assertIn("前往訂票", movie)
        self.assertIn("場次入口", movie)
        self.assertIn("官方網站", movie)
        self.assertIn("txtSessionId=abc", movie)

        match = re_search_href(movie, "在地圖查看影城位置")
        query = parse_qs(urlparse(match).query)
        self.assertEqual(query["restore"], ["1"])
        self.assertEqual(urlparse(match).path, "index.html")
        self.assertEqual(query["movie"], ["測試動畫"])
        self.assertEqual(query["date"], ["2026-10-06"])

        upcoming = (self.web / "movie-2.html").read_text(encoding="utf-8")
        self.assertIn("目前沒有可查詢場次", upcoming)

        sitemap = (self.web / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("https://example.com/anime/movie-1.html", sitemap)
        robots = (self.web / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("https://example.com/anime/sitemap.xml", robots)


def re_search_href(document: str, label: str) -> str:
    import re

    match = re.search(rf'<a[^>]+href="([^"]+)"[^>]*>{re.escape(label)}</a>', document)
    if not match:
        raise AssertionError(f"link not found: {label}")
    return html_unescape(match.group(1))


def html_unescape(value: str) -> str:
    import html

    return html.unescape(value)


if __name__ == "__main__":
    unittest.main()
