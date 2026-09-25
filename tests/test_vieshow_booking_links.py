from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_movie_showtimes as crawler


class VieshowBookingLinkTests(unittest.TestCase):
    def test_session_value_builds_official_booking_url(self) -> None:
        value = "cinemacode=21&txtSessionId=165732"
        self.assertEqual(
            crawler.vieshow_booking_url_from_session_value(value),
            "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
            "?cinemacode=21&txtSessionId=165732",
        )

    def test_invalid_session_value_is_ignored(self) -> None:
        self.assertIsNone(crawler.vieshow_booking_url_from_session_value("165732"))

    def test_long_truncated_quick_booking_title_can_match_alias(self) -> None:
        self.assertTrue(
            crawler._vieshow_option_matches(
                "(數位)劇場版 很長很長的動畫電影標題前半段",
                ["劇場版 很長很長的動畫電影標題前半段與後半段完整版"],
            )
        )

    def test_enrichment_replaces_generic_vieshow_entry_with_session_url(self) -> None:
        record = crawler.ShowtimeRecord(
            location_id=7,
            show_date="2026-10-31",
            start_time="14:45",
            auditorium=None,
            format="(數位)測試電影 (普遍級)",
            language=None,
            booking_url=crawler.VIESHOW_URL,
            source_url=crawler.VIESHOW_URL,
            raw_text="(數位)測試電影 (普遍級)",
        )
        enriched = crawler._vieshow_record_with_booking(
            record,
            [
                {
                    "show_date": "2026-10-31",
                    "start_time": "14:45",
                    "movie_text": "(數位)測試電影",
                    "movie_value": "HO00000001",
                    "booking_url": (
                        "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                        "?cinemacode=1&txtSessionId=123456"
                    ),
                }
            ],
        )
        self.assertEqual(
            enriched.booking_url,
            "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
            "?cinemacode=1&txtSessionId=123456",
        )

    def test_ambiguous_same_time_without_format_match_keeps_generic_link(self) -> None:
        record = crawler.ShowtimeRecord(
            location_id=7,
            show_date="2026-10-31",
            start_time="14:45",
            auditorium=None,
            format="測試電影",
            language=None,
            booking_url=crawler.VIESHOW_URL,
            source_url=crawler.VIESHOW_URL,
            raw_text="測試電影",
        )
        enriched = crawler._vieshow_record_with_booking(
            record,
            [
                {
                    "show_date": "2026-10-31",
                    "start_time": "14:45",
                    "movie_text": "(IMAX)完全不同版本A",
                    "booking_url": "https://example.invalid/a",
                },
                {
                    "show_date": "2026-10-31",
                    "start_time": "14:45",
                    "movie_text": "(4DX)完全不同版本B",
                    "booking_url": "https://example.invalid/b",
                },
            ],
        )
        self.assertEqual(enriched.booking_url, crawler.VIESHOW_URL)


if __name__ == "__main__":
    unittest.main()
