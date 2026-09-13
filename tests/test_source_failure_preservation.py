from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_movie_showtimes as crawler  # noqa: E402


class SourceFailurePreservationTests(unittest.TestCase):
    def test_failed_source_does_not_clear_last_known_good_rows(self) -> None:
        conn = MagicMock()

        def failing_fetcher(*_args, **_kwargs):
            raise RuntimeError("temporary source outage")

        with patch.object(crawler, "start_run", return_value=77), patch.object(
            crawler, "finish_run"
        ) as finish_run, patch.object(crawler, "clear_source_showtimes") as clear_source:
            found, saved, error = crawler.run_source(
                conn,
                movie_id=1,
                source_name="測試影城",
                source_url="https://example.invalid/",
                fetcher=failing_fetcher,
                aliases=["測試電影"],
                show_date="2026-09-13",
            )

        self.assertEqual((found, saved), (0, 0))
        self.assertIn("temporary source outage", error or "")
        clear_source.assert_not_called()
        finish_run.assert_called_once()
        conn.commit.assert_called_once()

    def test_successful_empty_source_may_clear_stale_rows(self) -> None:
        conn = MagicMock()

        def empty_fetcher(*_args, **_kwargs):
            return []

        with patch.object(crawler, "start_run", return_value=78), patch.object(
            crawler, "finish_run"
        ), patch.object(crawler, "clear_source_showtimes") as clear_source, patch.object(
            crawler, "save_showtimes", return_value=0
        ):
            found, saved, error = crawler.run_source(
                conn,
                movie_id=1,
                source_name="測試影城",
                source_url="https://example.invalid/",
                fetcher=empty_fetcher,
                aliases=["測試電影"],
                show_date="2026-09-13",
            )

        self.assertEqual((found, saved, error), (0, 0, None))
        clear_source.assert_called_once_with(conn, 1, "2026-09-13", "測試影城")


if __name__ == "__main__":
    unittest.main()
