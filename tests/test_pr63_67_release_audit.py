from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
LOCATIONS = REPO / "web" / "data" / "locations.geojson"
VIESHOW_PREVIEWS = REPO / "web" / "data" / "vieshow_seat_previews.json"
APP_JS = REPO / "web" / "app.js"
DISCOVERY_JS = REPO / "web" / "discovery.js"
SEAT_JS = REPO / "web" / "seat-preview.js"
INDEX_HTML = REPO / "web" / "index.html"
SEAT_HTML = REPO / "web" / "seat-preview.html"

SHOWTIMES_RE = re.compile(
    r"^https://www\.showtimes\.com\.tw/ticketing/selectEvents/(\d+)/(\d+)\?date=(\d{4}-\d{2}-\d{2})$"
)


class PR63To67ReleaseAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.locations = json.loads(LOCATIONS.read_text(encoding="utf-8"))
        cls.previews = json.loads(VIESHOW_PREVIEWS.read_text(encoding="utf-8"))
        cls.app_js = APP_JS.read_text(encoding="utf-8")
        cls.discovery_js = DISCOVERY_JS.read_text(encoding="utf-8")
        cls.seat_js = SEAT_JS.read_text(encoding="utf-8")
        cls.index_html = INDEX_HTML.read_text(encoding="utf-8")
        cls.seat_html = SEAT_HTML.read_text(encoding="utf-8")

    def iter_showtimes(self):
        for title, by_date in (self.locations.get("movie_features_by_date") or {}).items():
            for show_date, features in (by_date or {}).items():
                for feature in features or []:
                    props = feature.get("properties") or {}
                    for showtime in props.get("showtimes") or []:
                        yield title, show_date, props, showtime

    def test_showtimes_public_data_is_all_new_date_level_links(self) -> None:
        urls = []
        old = []
        malformed = []
        target = []
        for title, show_date, props, showtime in self.iter_showtimes():
            if "秀泰" not in str(props.get("chain_name") or ""):
                continue
            url = str(showtime.get("booking_url") or "")
            urls.append(url)
            if "/ticketing?cid=" in url:
                old.append(url)
            match = SHOWTIMES_RE.fullmatch(url)
            if not match:
                malformed.append(url)
            if (
                title == "劇場版 吉伊卡哇 人魚島的秘密"
                and show_date == "2026-09-27"
                and props.get("location_name") == "大巨蛋秀泰影城"
            ):
                target.append((showtime.get("time"), url))

        self.assertGreater(len(urls), 0)
        self.assertEqual(old, [])
        self.assertEqual(malformed, [])
        self.assertEqual(
            sorted(target),
            [
                ("10:10", "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27"),
                ("12:00", "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27"),
                ("17:00", "https://www.showtimes.com.tw/ticketing/selectEvents/91/12763?date=2026-09-27"),
            ],
        )

    def test_vieshow_direct_sessions_have_complete_seat_snapshots(self) -> None:
        session_keys = set()
        generic = 0
        for _title, _date, props, showtime in self.iter_showtimes():
            if not re.search(r"威秀|VIESHOW|MUVIE", str(props.get("chain_name") or ""), re.I):
                continue
            url = str(showtime.get("booking_url") or "")
            parsed = urlparse(url)
            if (
                parsed.netloc.lower() == "www.vscinemas.com.tw"
                and parsed.path.lower() == "/vsticketing/ticketing/booking.aspx"
            ):
                query = parse_qs(parsed.query)
                cinema = (query.get("cinemacode") or [""])[0]
                session = (query.get("txtSessionId") or [""])[0]
                self.assertTrue(cinema and session, url)
                session_keys.add(f"{cinema}:{session}")
            elif "vscinemas.com.tw/ShowTimes" in url:
                generic += 1

        preview_keys = set((self.previews.get("previews") or {}).keys())
        self.assertGreater(len(session_keys), 0)
        self.assertEqual(self.previews.get("failure_count"), 0)
        self.assertEqual(session_keys, preview_keys)
        self.assertEqual(self.previews.get("preview_count"), len(preview_keys))
        # Generic fallback rows may exist when VIESHOW did not expose a session id.
        self.assertGreaterEqual(generic, 0)

    def test_vieshow_official_entry_and_booking_roles_are_separate(self) -> None:
        match = re.search(
            r"function officialWebsiteUrl\(\) \{(?P<body>.*?)\n\}",
            self.seat_js,
            re.S,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn('return "https://www.vscinemas.com.tw/";', body)
        self.assertNotIn("booking.aspx", body)

        self.assertIn(
            r"/vscinemas\.com\.tw\/vsTicketing\/ticketing\/booking\.aspx",
            self.app_js,
        )
        self.assertIn('if (officialLabel) officialLabel.textContent = "座位表入口";', self.app_js)

    def test_discovery_states_are_explicit_and_based_on_map_availability(self) -> None:
        self.assertIn('const MAP_DATA_URL = "data/locations.geojson";', self.discovery_js)
        self.assertIn('"今日剩餘場次已結束"', self.discovery_js)
        self.assertIn('"今天沒有排映場次"', self.discovery_js)
        self.assertIn('"目前沒有可查詢場次"', self.discovery_js)
        self.assertIn("availabilityDatesForItem", self.discovery_js)

    def test_cache_versions_include_all_merged_frontend_fixes(self) -> None:
        self.assertIn('app.js?v=20260927b', self.index_html)
        self.assertIn('discovery.js?v=20260926c', self.index_html)
        self.assertIn('seat-preview.js?v=20260927a', self.seat_html)

    def test_showtimes_frontend_whitelist_accepts_select_events_only(self) -> None:
        self.assertIn("showtimes\\.com\\.tw\\/ticketing\\/selectEvents", self.app_js)
        self.assertNotIn(
            r"showtimes\.com\.tw\/ticketing\?cid=",
            self.app_js,
        )


if __name__ == "__main__":
    unittest.main()
