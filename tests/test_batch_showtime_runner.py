from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import fetch_movie_showtimes_batch_runner as batch_runner  # noqa: E402
import update_map  # noqa: E402


class BatchShowtimeRunnerTests(unittest.TestCase):
    def test_run_movie_restores_argv_and_passes_aliases_dates_and_db(self) -> None:
        original_argv = list(sys.argv)
        with patch.object(batch_runner.crawler, "main") as crawler_main:
            batch_runner.run_movie(
                "測試電影",
                dates=["2026-09-13", "2026-09-14"],
                aliases=["測試別名"],
                db=Path("tmp/test.sqlite"),
            )
            crawler_main.assert_called_once_with()
            called_argv = crawler_main.call_args
            self.assertIsNotNone(called_argv)
        self.assertEqual(sys.argv, original_argv)

    def test_batch_main_keeps_crawler_module_cache_between_movies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            movie_list = Path(temp_dir) / "movies.txt"
            movie_list.write_text("第一部\n第二部\n", encoding="utf-8")
            seen: list[list[str]] = []

            def fake_crawler_main() -> None:
                if not seen:
                    batch_runner.crawler._REQUEST_CACHE[("sentinel",)] = b"cached"
                else:
                    self.assertEqual(
                        batch_runner.crawler._REQUEST_CACHE.get(("sentinel",)),
                        b"cached",
                    )
                seen.append(list(sys.argv))

            argv = [
                "fetch_movie_showtimes_batch_runner.py",
                "--movie-list",
                str(movie_list),
                "--date",
                "2026-09-13",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                batch_runner.crawler, "main", side_effect=fake_crawler_main
            ), patch.object(batch_runner, "aliases_for_titles", return_value={"第一部": [], "第二部": []}):
                batch_runner.main()

            self.assertEqual(len(seen), 2)
            self.assertEqual(seen[0][1], "第一部")
            self.assertEqual(seen[1][1], "第二部")

    def test_update_map_builds_one_batch_command_for_all_dates(self) -> None:
        command = update_map.build_batch_fetch_args(
            Path("電影清單.txt"),
            ["2026-09-13", "2026-09-14", "2026-09-15"],
        )
        self.assertEqual(command[0], "scripts/fetch_movie_showtimes_batch_runner.py")
        self.assertEqual(command.count("--movie-list"), 1)
        self.assertEqual(command.count("--date"), 3)
        self.assertNotIn("scripts/fetch_movie_showtimes_runner.py", command)


if __name__ == "__main__":
    unittest.main()
