from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts.madou_atmovies_fallback import collect_madou_records


MOVIES = [{"title": "劇場版 吉伊卡哇 人魚島的秘密", "aliases": []}]
SOURCE_CONFIG = {
    "sources": [
        {
            "location_id": 104,
            "name": "麻豆戲院",
            "url_template": "https://www.atmovies.com.tw/showtime/t06625/a06/{date}/",
            "fallback_url_templates": [
                "https://origin.atmovies.com.tw/showtime/t06625/a06/{date}/",
                "https://cdn.atmovies.com.tw/showtime/t06625/a06/{date}/",
            ],
            "enabled": True,
        }
    ]
}
SOCIAL_CONFIG = {
    "sources": [
        {
            "location_id": 104,
            "official_url": "https://www.facebook.com/196018270491462",
            "social_urls": ["https://www.instagram.com/madoucinema/"],
        }
    ]
}


def valid_page(show_date: str, time_value: str = "18：20") -> bytes:
    year, month, day = show_date.split("-")
    return (
        f"<html><body><h3>{year}/{month}/{day}</h3>"
        "<div>劇場版 吉伊卡哇 人魚島的秘密</div>"
        f"<div>{time_value}</div><div>其他戲院(10)</div>"
        "</body></html>"
    ).encode("utf-8")


class MadouFallbackTests(unittest.TestCase):
    @patch("scripts.madou_atmovies_fallback.MAX_SOURCE_LOOKAHEAD_DAYS", 0)
    def test_uses_origin_when_primary_host_fails(self):
        def fetcher(url: str) -> bytes:
            if "www.atmovies.com.tw" in url:
                raise RuntimeError("502 Bad Gateway")
            if "origin.atmovies.com.tw" in url:
                return valid_page("2026-09-14")
            raise AssertionError(f"unexpected fetch: {url}")

        records, success, failure = collect_madou_records(
            primary_date="2026-09-14",
            movies=MOVIES,
            source_config=SOURCE_CONFIG,
            social_config=SOCIAL_CONFIG,
            fetcher=fetcher,
        )
        key = (MOVIES[0]["title"], "2026-09-14", 104)
        self.assertEqual(success, 1)
        self.assertEqual(failure, 0)
        self.assertIn(key, records)
        self.assertIn("origin.atmovies.com.tw", records[key][0])
        self.assertEqual(records[key][1][0]["time"], "18:20")

    @patch("scripts.madou_atmovies_fallback.MAX_SOURCE_LOOKAHEAD_DAYS", 0)
    def test_stale_primary_page_does_not_block_next_mirror(self):
        def fetcher(url: str) -> bytes:
            if "www.atmovies.com.tw" in url:
                return valid_page("2026-09-13")
            if "origin.atmovies.com.tw" in url:
                return valid_page("2026-09-14", "20：10")
            raise AssertionError(f"unexpected fetch: {url}")

        records, success, failure = collect_madou_records(
            primary_date="2026-09-14",
            movies=MOVIES,
            source_config=SOURCE_CONFIG,
            social_config=SOCIAL_CONFIG,
            fetcher=fetcher,
        )
        key = (MOVIES[0]["title"], "2026-09-14", 104)
        self.assertEqual((success, failure), (1, 0))
        self.assertEqual(records[key][1][0]["time"], "20:10")

    @patch("scripts.madou_atmovies_fallback.MAX_SOURCE_LOOKAHEAD_DAYS", 0)
    def test_all_mirrors_failed_reports_social_required_without_deleting(self):
        def fetcher(url: str) -> bytes:
            raise RuntimeError("upstream unavailable")

        output = io.StringIO()
        with redirect_stdout(output):
            records, success, failure = collect_madou_records(
                primary_date="2026-09-14",
                movies=MOVIES,
                source_config=SOURCE_CONFIG,
                social_config=SOCIAL_CONFIG,
                fetcher=fetcher,
            )
        self.assertEqual(records, {})
        self.assertEqual((success, failure), (0, 1))
        text = output.getvalue()
        self.assertIn("[social-required]", text)
        self.assertIn("facebook.com/196018270491462", text)
        self.assertIn("instagram.com/madoucinema", text)


if __name__ == "__main__":
    unittest.main()
