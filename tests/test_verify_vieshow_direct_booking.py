from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import verify_vieshow_direct_booking as verify  # noqa: E402


def feature(chain: str, showtimes: list[dict]) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "chain_name": chain,
            "location_name": "測試館",
            "showtimes": showtimes,
        },
        "geometry": {"type": "Point", "coordinates": [121.5, 25.0]},
    }


class VerifyVieshowDirectBookingTests(unittest.TestCase):
    def test_counts_direct_booking_links(self) -> None:
        payload = {
            "features": [
                feature(
                    "威秀影城 / VIESHOW",
                    [
                        {
                            "time": "19:00",
                            "booking_url": (
                                "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                                "?cinemacode=1&txtSessionId=123"
                            ),
                        },
                        {
                            "time": "21:00",
                            "booking_url": "https://www.vscinemas.com.tw/ShowTimes/",
                        },
                    ],
                ),
                feature(
                    "其他影城",
                    [{"time": "20:00", "booking_url": "https://example.test/"}],
                ),
            ]
        }
        self.assertEqual(
            verify.inspect(payload),
            {
                "vieshow_venues": 1,
                "vieshow_showtimes": 2,
                "direct_booking_showtimes": 1,
            },
        )

    def test_multimovie_export_is_verified_from_movie_features_by_date(self) -> None:
        direct = feature(
            "威秀影城 / VIESHOW",
            [{
                "time": "19:25",
                "booking_url": (
                    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                    "?cinemacode=1&txtSessionId=321"
                ),
            }],
        )
        generic = feature(
            "威秀影城 / VIESHOW",
            [{
                "time": "21:40",
                "booking_url": "https://www.vscinemas.com.tw/ShowTimes/",
            }],
        )
        direct["properties"]["location_id"] = 1
        direct["properties"]["show_date"] = "2026-09-26"
        generic["properties"]["location_id"] = 2
        generic["properties"]["show_date"] = "2026-09-26"
        payload = {
            "movie_features_by_date": {
                "電影A": {"2026-09-26": [direct]},
                "電影B": {"2026-09-26": [generic]},
            },
            "features": [],
        }
        self.assertEqual(
            verify.inspect(payload),
            {
                "vieshow_venues": 2,
                "vieshow_showtimes": 2,
                "direct_booking_showtimes": 1,
            },
        )

    def test_muvie_is_treated_as_vieshow(self) -> None:
        payload = {
            "features": [
                feature(
                    "MUVIE CINEMAS",
                    [
                        {
                            "time": "18:00",
                            "booking_url": (
                                "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                                "?cinemacode=31&txtSessionId=999"
                            ),
                        }
                    ],
                )
            ]
        }
        self.assertEqual(verify.inspect(payload)["direct_booking_showtimes"], 1)

    def test_generic_showtimes_url_is_not_direct(self) -> None:
        self.assertFalse(
            verify.is_direct_booking("https://www.vscinemas.com.tw/ShowTimes/")
        )


if __name__ == "__main__":
    unittest.main()
