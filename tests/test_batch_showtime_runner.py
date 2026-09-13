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

    def test_dynamic_select_render_is_cached_across_movies(self) -> None:
        batch_runner.cached_render_select_option_html.cache_clear()
        with patch.object(
            batch_runner,
            "_original_render_select_option_html",
            return_value="<html>cached</html>",
        ) as original_render:
            first = batch_runner.cached_render_select_option_html(
                "https://example.invalid/time",
                "#date",
                "2026-09-13",
            )
            second = batch_runner.cached_render_select_option_html(
                "https://example.invalid/time",
                "#date",
                "2026-09-13",
            )

        self.assertEqual(first, second)
        original_render.assert_called_once_with(
            "https://example.invalid/time",
            "#date",
            "2026-09-13",
            2500,
        )

    def test_same_run_failure_cache_skips_second_ace_timeout(self) -> None:
        batch_runner._same_run_failure_cache.clear()
        url = "https://www.acecinema.com.tw/movie/now"
        with patch.object(
            batch_runner,
            "_original_request_bytes",
            side_effect=TimeoutError("official timeout"),
        ) as original_request:
            with self.assertRaises(TimeoutError):
                batch_runner.request_bytes_with_same_run_failure_cache(url)
            with self.assertRaisesRegex(RuntimeError, "same_run_cached_failure"):
                batch_runner.request_bytes_with_same_run_failure_cache(url)
        self.assertEqual(original_request.call_count, 1)

    def test_same_run_failure_cache_does_not_apply_to_fallback_host(self) -> None:
        batch_runner._same_run_failure_cache.clear()
        url = "https://www.atmovies.com.tw/showtime/example/"
        with patch.object(
            batch_runner,
            "_original_request_bytes",
            side_effect=TimeoutError("fallback timeout"),
        ) as original_request:
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    batch_runner.request_bytes_with_same_run_failure_cache(url)
        self.assertEqual(original_request.call_count, 2)

    def test_shin_kong_double_failure_is_re_raised(self) -> None:
        def failing_fallback(*_args, **_kwargs):
            raise RuntimeError("fallback down")

        def legacy_adapter(*_args, **_kwargs):
            try:
                batch_runner.crawler.fetch_skcinemas_atmovies([], [], "2026-09-13")
            except RuntimeError:
                return []
            return []

        with patch.object(
            batch_runner,
            "_original_fetch_skcinemas_atmovies",
            side_effect=failing_fallback,
        ), patch.object(batch_runner, "_original_fetch_skcinemas", side_effect=legacy_adapter):
            with self.assertRaisesRegex(RuntimeError, "last-known-good"):
                batch_runner.safe_fetch_skcinemas(None, ["測試電影"], "2026-09-13")

    def test_shin_kong_successful_empty_fallback_remains_empty_success(self) -> None:
        def empty_fallback(*_args, **_kwargs):
            return []

        def legacy_adapter(*_args, **_kwargs):
            return batch_runner.crawler.fetch_skcinemas_atmovies([], [], "2026-09-13")

        with patch.object(
            batch_runner,
            "_original_fetch_skcinemas_atmovies",
            side_effect=empty_fallback,
        ), patch.object(batch_runner, "_original_fetch_skcinemas", side_effect=legacy_adapter):
            self.assertEqual(
                batch_runner.safe_fetch_skcinemas(None, ["測試電影"], "2026-09-13"),
                [],
            )

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
