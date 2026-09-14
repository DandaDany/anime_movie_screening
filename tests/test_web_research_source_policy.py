from __future__ import annotations

import unittest

from scripts.web_research_source_policy import (
    build_location_source_policy,
    source_url_allowed,
    validate_payload_sources,
)


class WebResearchSourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.master = {
            "chains": [
                {
                    "id": 9,
                    "official_url": "https://www.broadway-cineplex.com.tw/",
                    "crawl_url": "https://www.broadway-cineplex.com.tw/book.html",
                    "booking_url": None,
                    "active": True,
                },
                {
                    "id": 40,
                    "official_url": None,
                    "crawl_url": None,
                    "booking_url": None,
                    "active": True,
                },
            ],
            "locations": [
                {
                    "id": 51,
                    "chain_id": 9,
                    "location_url": "https://www.broadway-cineplex.com.tw/book.html?obj=Taipei",
                    "source_url": None,
                    "active": True,
                },
                {
                    "id": 104,
                    "chain_id": 40,
                    "location_url": "https://www.facebook.com/pages/%E9%BA%BB%E8%B1%86%E6%88%B2%E9%99%A2/196018270491462",
                    "source_url": "https://www.atmovies.com.tw/showtime/t06625/a06/",
                    "active": True,
                },
            ],
        }
        self.supplemental = {
            "sources": [
                {
                    "location_id": 51,
                    "url_template": "https://www.atmovies.com.tw/showtime/t02c01/a02/{date}/",
                    "enabled": True,
                }
            ]
        }
        self.social = {
            "sources": [
                {
                    "location_id": 104,
                    "official_url": None,
                    "social_urls": [
                        "https://www.facebook.com/pages/%E9%BA%BB%E8%B1%86%E6%88%B2%E9%99%A2/196018270491462",
                        "https://www.instagram.com/madoucinema/",
                    ],
                    "deterministic_fallback": "https://www.atmovies.com.tw/showtime/t06625/a06/{date}/",
                }
            ]
        }
        self.policy = build_location_source_policy(self.master, self.supplemental, self.social)

    def test_accepts_location_specific_atmovies_fallback(self):
        self.assertTrue(
            source_url_allowed(
                "https://www.atmovies.com.tw/showtime/t02c01/a02/20260914/",
                self.policy[51],
            )
        )

    def test_rejects_wrong_atmovies_cinema_code(self):
        self.assertFalse(
            source_url_allowed(
                "https://www.atmovies.com.tw/showtime/t06625/a06/20260914/",
                self.policy[51],
            )
        )

    def test_accepts_configured_official_domain(self):
        self.assertTrue(
            source_url_allowed(
                "https://www.broadway-cineplex.com.tw/Movie/GetMovieList/Taipei",
                self.policy[51],
            )
        )

    def test_accepts_social_post_only_for_social_configured_location(self):
        self.assertTrue(source_url_allowed("https://www.instagram.com/p/ABC123/", self.policy[104]))
        self.assertFalse(source_url_allowed("https://www.instagram.com/p/ABC123/", self.policy[51]))

    def test_rejects_arbitrary_example_domain(self):
        payload = {
            "records": [
                {"location_id": 51, "source_url": "https://example.com/post"}
            ]
        }
        with self.assertRaises(ValueError):
            validate_payload_sources(payload, self.master, self.policy)

    def test_accepts_authorized_payload_source(self):
        payload = {
            "records": [
                {
                    "location_id": 51,
                    "source_url": "https://www.atmovies.com.tw/showtime/t02c01/a02/20260914/",
                }
            ]
        }
        self.assertEqual(validate_payload_sources(payload, self.master, self.policy), 1)


if __name__ == "__main__":
    unittest.main()
