from __future__ import annotations

import unittest

from scripts.supplemental_web_update import merge_records_into_geojson


class BroadwayCanonicalMergeTests(unittest.TestCase):
    def test_atmovies_fallback_merges_into_existing_location_51_without_second_pin(self):
        title = "劇場版 吉伊卡哇 人魚島的秘密"
        show_date = "2026-09-14"
        official_feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [121.536644362629, 25.010805770294]},
            "properties": {
                "location_id": 51,
                "chain_name": "百老匯影城",
                "location_name": "公館百老匯影城",
                "map_name": "百老匯影城 公館百老匯影城",
                "address": "台北市文山區羅斯福路四段200號",
                "city": "臺北市",
                "movie_title": title,
                "show_date": show_date,
                "showtime_count": 1,
                "showtimes": [
                    {
                        "time": "10:50",
                        "format": "數位/日語",
                        "language": "日語",
                        "auditorium": "1廳",
                        "booking_url": "https://www.broadway-cineplex.com.tw/",
                        "label": "10:50 數位/日語",
                    }
                ],
                "start_times": "10:50",
            },
        }
        payload = {
            "movie_features_by_date": {title: {show_date: [official_feature]}},
            "movies": [{"title": title}],
        }
        master = {
            "chains": [
                {
                    "id": 9,
                    "chain_name": "百老匯影城",
                    "official_url": "https://www.broadway-cineplex.com.tw/",
                    "active": True,
                }
            ],
            "locations": [
                {
                    "id": 51,
                    "chain_id": 9,
                    "location_name": "公館百老匯影城",
                    "display_name": None,
                    "address": "台北市文山區羅斯福路四段200號",
                    "city": "台北市",
                    "latitude": 25.010805770294,
                    "longitude": 121.536644362629,
                    "location_url": "https://www.broadway-cineplex.com.tw/",
                    "active": True,
                }
            ],
        }
        records = {
            (title, show_date, 51): (
                "https://www.atmovies.com.tw/showtime/t02c01/a02/20260914/",
                [
                    {"time": "10:50", "format": title, "language": None, "auditorium": None},
                    {"time": "17:25", "format": title, "language": None, "auditorium": None},
                ],
            )
        }

        merged, features_added, showtimes_added = merge_records_into_geojson(
            payload,
            primary_date=show_date,
            movies=[{"title": title, "aliases": []}],
            records=records,
            master=master,
        )

        features = merged["movie_features_by_date"][title][show_date]
        self.assertEqual(features_added, 0)
        self.assertEqual(showtimes_added, 1)
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]["properties"]["location_id"], 51)
        self.assertTrue(features[0]["properties"]["supplemental_web_source"])
        self.assertEqual(
            [item["time"] for item in features[0]["properties"]["showtimes"]],
            ["10:50", "17:25"],
        )


if __name__ == "__main__":
    unittest.main()
