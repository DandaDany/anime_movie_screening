from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_vieshow_seat_previews as seats


class VieshowSeatPreviewTests(unittest.TestCase):
    def test_parse_booking_url(self) -> None:
        self.assertEqual(
            seats.parse_booking_url(
                "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                "?cinemacode=21&txtSessionId=165732"
            ),
            ("21", "165732"),
        )
        self.assertIsNone(
            seats.parse_booking_url("https://www.vscinemas.com.tw/ShowTimes/")
        )

    def test_parse_preview_html(self) -> None:
        html = """
        <html><body>
          <span id="LabelMovie_strName">測試電影</span>
          <span id="LabelMovie_strNameEn">TEST MOVIE</span>
          <span id="LabelSession_dtmDateTime">2026-09-25 19:25</span>
          <span id="LabelCinema_strName">台北信義威秀影城</span>
          <span id="LabelScreen_strName">第7廳</span>
          <table id="GridViewSessionSeats">
            <tr>
              <td><div class="DivSeat"><div class="label label-info" data-toggle="tooltip" title="A01">A</div></div></td>
              <td><div class="DivSeat"><img src="images/Null.png"></div></td>
              <td><div class="DivSeat"><div class="label label-danger" data-toggle="tooltip" title="A02">A</div></div></td>
              <td><div class="DivSeat"><img src="Images/wheelchair_available.png" alt="輪椅位"></div></td>
            </tr>
          </table>
        </body></html>
        """
        preview = seats.parse_preview_html(html, "1", "1878613")
        assert preview is not None
        self.assertEqual(preview["key"], "1:1878613")
        self.assertEqual(preview["available"], 1)
        self.assertEqual(preview["sold"], 1)
        self.assertEqual(preview["ordinary_seats"], 2)
        self.assertEqual(preview["wheelchair"], 1)
        self.assertEqual(
            [cell["type"] for cell in preview["rows"][0]],
            ["available", "gap", "sold", "wheelchair"],
        )
        self.assertEqual(preview["rows"][0][0]["seat"], "A01")
        self.assertEqual(preview["rows"][0][2]["seat"], "A02")

    def test_collect_booking_urls_from_geojson(self) -> None:
        payload = """{
          "type": "FeatureCollection",
          "features": [{
            "type": "Feature",
            "properties": {
              "showtimes": [
                {
                  "time": "19:25",
                  "booking_url": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111"
                },
                {
                  "time": "21:40",
                  "booking_url": "https://www.vscinemas.com.tw/ShowTimes/"
                },
                {
                  "time": "22:00",
                  "booking_url": "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx?cinemacode=1&txtSessionId=111"
                }
              ]
            },
            "geometry": {"type": "Point", "coordinates": [121.5, 25.0]}
          }]
        }"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locations.geojson"
            path.write_text(payload, encoding="utf-8")
            self.assertEqual(
                seats.collect_booking_urls(path),
                [
                    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
                    "?cinemacode=1&txtSessionId=111"
                ],
            )


if __name__ == "__main__":
    unittest.main()
