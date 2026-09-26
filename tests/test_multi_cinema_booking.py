from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import export_geojson


class MultiCinemaBookingExportTests(unittest.TestCase):
    def test_century_exact_session_exposes_seat_preview(self):
        url = (
            "https://ticket.centuryasia.com.tw/Ximen/buyticket_process.aspx"
            "?ProgramID=0000215&eventsn=90&computerid=16358"
        )
        self.assertEqual(
            export_geojson.showtime_seat_preview_url("喜樂時代影城", url),
            url,
        )

    def test_century_generic_page_has_no_seat_preview(self):
        self.assertIsNone(
            export_geojson.showtime_seat_preview_url(
                "喜樂時代影城",
                "https://www.centuryasia.com.tw/book.html?sid=Nangang",
            )
        )

    def test_broadway_session_tuple_fallback_maps_to_quick_view(self):
        session_tuple_url = (
            "https://www.broadway-cineplex.com.tw/book.html"
            "?obj=Zhubei,0000946,2026-09-26,19-20,0010"
        )
        self.assertEqual(
            export_geojson.showtime_seat_preview_url("百老匯影城", session_tuple_url),
            "https://www.broadway-cineplex.com.tw/quick-view.html"
            "?obj=Zhubei,0000946,2026-09-26,19-20,0010",
        )

    def test_broadway_cinema_only_entry_has_no_seat_preview(self):
        self.assertIsNone(
            export_geojson.showtime_seat_preview_url(
                "百老匯影城",
                "https://www.broadway-cineplex.com.tw/book.html?obj=Zhubei",
            )
        )


if __name__ == "__main__":
    unittest.main()
