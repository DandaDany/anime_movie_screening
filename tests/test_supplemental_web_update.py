from __future__ import annotations

import unittest

from scripts.preserve_supplemental_geojson import preserve_supplemental_features
from scripts.supplemental_web_update import (
    cm_movie_article_urls,
    merge_feature,
    merge_records_into_geojson,
    parse_atmovies_page,
    parse_cm_movie_detail_page,
)


class SupplementalAtMoviesParserTests(unittest.TestCase):
    def test_parses_only_requested_date_and_tracked_title(self):
        raw = """
        <html><body><h3>2026/09/13 (日)</h3>
        <div>劇場版 吉伊卡哇 人魚島的秘密</div><div>片長：95分</div>
        <div>10：20</div><div>12:40</div><div>其他戲院(30)</div>
        <div>完全不同的電影</div><div>15：00</div><div>其他戲院(10)</div>
        </body></html>
        """.encode("utf-8")
        movies = [{"title": "劇場版 吉伊卡哇 人魚島的秘密", "aliases": []}]
        parsed = parse_atmovies_page(raw, "2026-09-13", movies)
        self.assertEqual([item["time"] for item in parsed[movies[0]["title"]]], ["10:20", "12:40"])

    def test_stale_or_redirected_date_fails_closed(self):
        raw = """<html><body><h3>2026/09/12 (六)</h3><div>劇場版 吉伊卡哇 人魚島的秘密</div><div>10：20</div><div>其他戲院(30)</div></body></html>""".encode("utf-8")
        movies = [{"title": "劇場版 吉伊卡哇 人魚島的秘密", "aliases": []}]
        self.assertEqual(parse_atmovies_page(raw, "2026-09-13", movies), {})

    def test_alias_can_match_source_title(self):
        raw = """<html><body><h3>2026/09/13 (日)</h3><div>電影哆啦A夢：新‧大雄的海底鬼岩城</div><div>08：30</div><div>其他戲院(5)</div></body></html>""".encode("utf-8")
        movies = [{"title": "電影哆啦A夢：新．大雄的海底鬼岩城", "aliases": ["電影哆啦A夢：新‧大雄的海底鬼岩城"]}]
        parsed = parse_atmovies_page(raw, "2026-09-13", movies)
        self.assertEqual(parsed[movies[0]["title"]][0]["time"], "08:30")


class SupplementalCmMovieParserTests(unittest.TestCase):
    def test_parses_explicit_date_ranges_within_supported_window(self):
        raw = """
        <html><body><h1>希望:末日血戰</h1>
        <p>9/4至9/5 13:00、17:00</p>
        <p>9/8至9/10 11:00、15:10</p>
        <p>語言: 韓語</p>
        </body></html>
        """.encode("utf-8")
        parsed = parse_cm_movie_detail_page(
            raw,
            ["2026-09-09", "2026-09-10", "2026-09-11"],
        )
        self.assertEqual(sorted(parsed), ["2026-09-09", "2026-09-10"])
        self.assertEqual(
            [item["time"] for item in parsed["2026-09-09"]],
            ["11:00", "15:10"],
        )
        self.assertEqual(parsed["2026-09-09"][0]["language"], "韓語")
        self.assertIsNone(parsed["2026-09-09"][0]["format"])

    def test_discovers_only_tracked_movie_articles(self):
        raw = """
        <html><body>
        <article><h2><a href="/2026/09/01/tracked/">希望:末日血戰</a></h2></article>
        <article><h2><a href="/2026/09/01/other/">其他電影</a></h2></article>
        </body></html>
        """.encode("utf-8")
        movies = [{"title": "希望：末日血戰", "aliases": ["希望:末日血戰"]}]
        urls = cm_movie_article_urls(raw, movies, "https://www.cm-movie.com.tw/category/time/")
        self.assertEqual(
            urls,
            {"希望：末日血戰": "https://www.cm-movie.com.tw/2026/09/01/tracked/"},
        )

    def test_old_post_dates_fail_closed(self):
        raw = "<html><body><p>8/1 10:00、12:00</p></body></html>".encode("utf-8")
        self.assertEqual(
            parse_cm_movie_detail_page(raw, ["2026-09-15", "2026-09-16"]),
            {},
        )


class SupplementalGeoJsonMergeTests(unittest.TestCase):
    def test_merge_does_not_delete_first_pass_showtimes(self):
        existing = {
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [121.0, 25.0]},
            "properties": {"location_id": 68, "showtime_count": 1, "showtimes": [{"time": "10:00", "format": None, "language": None, "auditorium": None, "booking_url": "first", "label": "10:00"}], "start_times": "10:00"},
        }
        incoming = {
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [121.1, 25.1]},
            "properties": {"location_id": 68, "chain_name": "美麗新影城", "location_name": "台北大直美麗新皇家影城", "map_name": "美麗新影城 台北大直美麗新皇家影城", "address": "x", "city": "臺北市", "location_url": "source", "official_url": "official", "crawl_url": "fallback", "movie_title": "電影", "show_date": "2026-09-13", "showtime_count": 2, "showtimes": [{"time": "10:00", "format": "電影", "language": None, "auditorium": None, "booking_url": "fallback", "label": "10:00 電影"}, {"time": "12:00", "format": "電影", "language": None, "auditorium": None, "booking_url": "fallback", "label": "12:00 電影"}], "start_times": "10:00, 12:00"},
        }
        merged, added = merge_feature(existing, incoming)
        self.assertEqual(added, 1)
        self.assertEqual([item["time"] for item in merged["properties"]["showtimes"]], ["10:00", "12:00"])

    def test_real_supplement_replaces_unavailable_placeholder(self):
        existing = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [120.3, 22.6]}, "properties": {"location_id": 72, "showtime_count": 0, "showtimes": [], "showtime_unavailable": True, "showtime_unavailable_reason": "blocked"}}
        incoming = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [120.3, 22.6]}, "properties": {"location_id": 72, "chain_name": "高雄環球影城", "location_name": "高雄環球影城", "map_name": "高雄環球影城 高雄環球影城", "address": "x", "city": "高雄市", "location_url": "source", "official_url": "official", "crawl_url": "fallback", "movie_title": "電影", "show_date": "2026-09-13", "showtime_count": 1, "showtimes": [{"time": "18:00", "format": None, "language": None, "auditorium": None, "booking_url": "fallback", "label": "18:00"}], "start_times": "18:00"}}
        merged, _ = merge_feature(existing, incoming)
        self.assertNotIn("showtime_unavailable", merged["properties"])
        self.assertEqual(merged["properties"]["showtime_count"], 1)

    def test_0600_promotes_today_from_yesterdays_future_bucket(self):
        title = "電影"
        old_feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [121.0, 25.0]}, "properties": {"location_id": 1, "showtime_count": 1, "showtimes": [{"time": "09:00"}]}}
        payload = {"movie_title": title, "show_date": "2026-09-12", "movies": [], "movie_features": {}, "movie_features_by_date": {title: {"2026-09-12": [], "2026-09-13": [old_feature]}}, "available_dates": ["2026-09-12", "2026-09-13"], "features": []}
        master = {"chains": [{"id": 1, "chain_name": "A", "official_url": None, "active": True}], "locations": [{"id": 1, "chain_id": 1, "location_name": "A", "display_name": None, "address": "x", "city": "台北市", "latitude": 25.0, "longitude": 121.0, "location_url": None, "active": True}]}
        merged, _, _ = merge_records_into_geojson(payload, primary_date="2026-09-13", movies=[{"title": title, "aliases": []}], records={}, master=master)
        self.assertEqual(merged["show_date"], "2026-09-13")
        self.assertEqual(merged["features"][0]["properties"]["location_id"], 1)
        self.assertNotIn("2026-09-12", merged["movie_features_by_date"][title])

    def test_0700_preserves_verified_0600_social_feature(self):
        social_feature = {
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [120.19665, 22.99297]},
            "properties": {"location_id": 115, "movie_title": "電影", "show_date": "2026-09-13", "showtime_count": 1, "showtimes": [{"time": "19:00", "format": None, "language": "日語", "auditorium": None, "booking_url": "social", "label": "19:00"}], "start_times": "19:00", "supplemental_web_source": True},
        }
        previous = {"movie_features_by_date": {"電影": {"2026-09-13": [social_feature]}}}
        target = {"movie_features_by_date": {"電影": {"2026-09-13": []}}}
        merged, features, showtimes = preserve_supplemental_features(target, previous, "2026-09-13")
        self.assertEqual(features, 1)
        self.assertEqual(showtimes, 1)
        self.assertEqual(merged["movie_features_by_date"]["電影"]["2026-09-13"][0]["properties"]["location_id"], 115)


if __name__ == "__main__":
    unittest.main()
