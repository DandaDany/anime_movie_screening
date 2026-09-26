from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import fetch_movie_showtimes as showtimes  # noqa: E402


class ShowTimesBookingUrlTests(unittest.TestCase):
    def test_builds_cinema_movie_date_level_booking_url(self) -> None:
        self.assertEqual(
            showtimes.showtimes_date_booking_url(91, 12763, "2026-09-27"),
            "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27",
        )


if __name__ == "__main__":
    unittest.main()
