from __future__ import annotations

import json
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
MASTER_PATH = PROJECT_DIR / "data" / "control" / "cinema_master.json"
LOGOS_PATH = PROJECT_DIR / "web" / "data" / "chain_logos.json"
SOCIAL_PATH = PROJECT_DIR / "data" / "input" / "social_showtime_sources.json"

NEW_LOCATION_IDS = set(range(98, 116))
NEW_CHAIN_NAMES = {
    "星橋國際影城",
    "日日新影城",
    "全球影城",
    "員林影城",
    "嘉年華戲院",
    "全美戲院",
    "麻豆戲院",
    "景美佳佳戲院",
    "光點台北電影院",
    "府中15",
    "國家電影及視聽文化中心",
    "桃園光影文化館",
    "中壢光影電影館",
    "中山73影視藝文空間",
    "高雄市電影館",
    "內惟藝術中心",
    "花蓮鐵道電影院",
    "今日戲院",
}


class NewCinemaMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        cls.logos = json.loads(LOGOS_PATH.read_text(encoding="utf-8"))
        cls.social = json.loads(SOCIAL_PATH.read_text(encoding="utf-8"))
        cls.chain_by_id = {int(item["id"]): item for item in cls.master["chains"]}
        cls.location_by_id = {int(item["id"]): item for item in cls.master["locations"]}
        cls.social_by_location = {
            int(item["location_id"]): item for item in cls.social.get("sources", [])
        }

    def test_all_new_locations_have_coordinates_and_are_active(self):
        self.assertEqual(NEW_LOCATION_IDS, NEW_LOCATION_IDS & self.location_by_id.keys())
        for location_id in sorted(NEW_LOCATION_IDS):
            location = self.location_by_id[location_id]
            self.assertTrue(location.get("active"), location["location_name"])
            self.assertIsNotNone(location.get("latitude"), location["location_name"])
            self.assertIsNotNone(location.get("longitude"), location["location_name"])

    def test_all_new_chain_names_have_logo_mapping(self):
        missing = sorted(NEW_CHAIN_NAMES - self.logos.keys())
        self.assertEqual(missing, [])
        for name in NEW_CHAIN_NAMES:
            self.assertTrue(str(self.logos[name]).strip(), name)

    def test_all_new_locations_have_public_official_social_or_source_link(self):
        missing: list[str] = []
        for location_id in sorted(NEW_LOCATION_IDS):
            location = self.location_by_id[location_id]
            chain = self.chain_by_id[int(location["chain_id"])]
            social = self.social_by_location.get(location_id, {})
            candidates = [
                chain.get("official_url"),
                location.get("location_url"),
                location.get("source_url"),
                social.get("official_url"),
                *((social.get("social_urls") or [])),
            ]
            if not any(str(value).strip() for value in candidates if value):
                missing.append(location["location_name"])
        self.assertEqual(missing, [])

    def test_verified_social_first_cinemas_have_official_social_entry(self):
        self.assertEqual(
            self.social_by_location[101]["official_url"],
            "https://www.facebook.com/YuanlinCinema",
        )
        self.assertEqual(
            self.social_by_location[104]["official_url"],
            "https://www.facebook.com/profile.php?id=61564946135169",
        )
        self.assertIn(
            "https://www.instagram.com/madoucinema/",
            self.social_by_location[104]["social_urls"],
        )


if __name__ == "__main__":
    unittest.main()
