from __future__ import annotations

import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_movie_showtimes as showtimes  # noqa: E402


ALIASES = ["蜘蛛人：重生日", "蜘蛛人 重生日"]


class VeniceFormatVersionTests(unittest.TestCase):
    def test_version_options_keep_each_variant_separate(self) -> None:
        html = """
        <select id="search_movie">
          <option value="">---</option>
          <option data-sn="2119" value="3374">蜘蛛人：重生日(2D-Atmos)</option>
          <option data-sn="2119" value="3376">蜘蛛人：重生日(3D-Atmos)</option>
          <option data-sn="2119" value="3389">蜘蛛人：重生日(2D - 水影威尼斯)</option>
          <option data-sn="9999" value="9999">別部電影(2D)</option>
        </select>
        """
        options = showtimes.venice_version_options(BeautifulSoup(html, "html.parser"), ALIASES)
        self.assertEqual(
            [title for title, _ in options],
            [
                "蜘蛛人：重生日(2D-Atmos)",
                "蜘蛛人：重生日(3D-Atmos)",
                "蜘蛛人：重生日(2D - 水影威尼斯)",
            ],
        )
        self.assertTrue(options[1][1].endswith("msn=3376&sn=2119"))

    def test_detail_parser_forces_exact_variant_and_date(self) -> None:
        html = """
        <html><body>
          <div>蜘蛛人：重生日(3D-Atmos)</div>
          <div>2026-09-25</div>
          <div>18:30</div>
          <div>21:10</div>
          <div>2026-09-26</div>
          <div>19:40</div>
        </body></html>
        """
        records = showtimes.parse_venice_detail_page(
            html,
            location_id=23,
            aliases=ALIASES,
            version_title="蜘蛛人：重生日(3D-Atmos)",
            show_date="2026-09-25",
            source_url="https://www.venice-cinemas.com.tw/showtime-view.php?msn=3376&sn=2119",
        )
        self.assertEqual([r.start_time for r in records], ["18:30", "21:10"])
        self.assertTrue(all(r.format == "蜘蛛人：重生日(3D-Atmos)" for r in records))
        self.assertTrue(all(r.language is None for r in records))

    def test_sibling_variants_do_not_collapse(self) -> None:
        two_d = showtimes.parse_venice_detail_page(
            "<div>蜘蛛人：重生日(2D-Atmos)</div><div>2026-09-25</div><div>18:00</div>",
            location_id=23,
            aliases=ALIASES,
            version_title="蜘蛛人：重生日(2D-Atmos)",
            show_date="2026-09-25",
            source_url="https://example.test/2d",
        )
        three_d = showtimes.parse_venice_detail_page(
            "<div>蜘蛛人：重生日(3D-Atmos)</div><div>2026-09-25</div><div>18:00</div>",
            location_id=23,
            aliases=ALIASES,
            version_title="蜘蛛人：重生日(3D-Atmos)",
            show_date="2026-09-25",
            source_url="https://example.test/3d",
        )
        keys = {(r.start_time, r.format) for r in [*two_d, *three_d]}
        self.assertEqual(
            keys,
            {
                ("18:00", "蜘蛛人：重生日(2D-Atmos)"),
                ("18:00", "蜘蛛人：重生日(3D-Atmos)"),
            },
        )


if __name__ == "__main__":
    unittest.main()
