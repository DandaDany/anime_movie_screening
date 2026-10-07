from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import submit_indexnow


class SubmitIndexNowTests(unittest.TestCase):
    def test_sitemap_payload_is_host_scoped_and_uses_public_key_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sitemap = Path(tmp) / "sitemap.xml"
            sitemap.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://dandadany.github.io/anime_movie_screening/</loc></url>
  <url><loc>https://dandadany.github.io/anime_movie_screening/movie-9.html</loc></url>
  <url><loc>https://example.com/not-ours</loc></url>
</urlset>
""",
                encoding="utf-8",
            )
            urls = submit_indexnow.sitemap_urls(sitemap)
            payload = submit_indexnow.build_payload(urls)

        self.assertEqual(payload["host"], "dandadany.github.io")
        self.assertEqual(payload["key"], submit_indexnow.INDEXNOW_KEY)
        self.assertEqual(
            payload["keyLocation"],
            "https://dandadany.github.io/anime_movie_screening/"
            + submit_indexnow.INDEXNOW_KEY
            + ".txt",
        )
        self.assertEqual(
            payload["urlList"],
            [
                "https://dandadany.github.io/anime_movie_screening/",
                "https://dandadany.github.io/anime_movie_screening/movie-9.html",
            ],
        )


if __name__ == "__main__":
    unittest.main()
