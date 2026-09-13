"""Batch production entrypoint for multiple tracked movies.

The legacy crawler is intentionally kept as the single source of parsing logic.  This
runner invokes it repeatedly *inside the same Python process* so its request/render/
VIESHOW caches survive between movies.  The previous update path spawned one fresh
process per movie, which repeated the expensive cinema-source crawl for every title
and scaled roughly linearly with the tracked movie count.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import fetch_movie_showtimes as crawler
from init_db import DEFAULT_DB_PATH
from movie_title_matching import aliases_for_titles, movie_matches, normalize_text
from update_map import read_movie_titles


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MOVIE_LIST = PROJECT_DIR / "電影清單.txt"

# Keep the same production-wide matching policy as the single-movie runner.
crawler.normalize_text = normalize_text
crawler.movie_matches = movie_matches


def run_movie(
    movie_title: str,
    *,
    dates: list[str],
    aliases: list[str],
    db: Path,
    keep_existing: bool = False,
    wipe_all: bool = False,
) -> None:
    """Invoke the existing crawler CLI in-process so module caches are retained."""
    argv = ["fetch_movie_showtimes_runner.py", movie_title]
    for alias in aliases:
        argv.extend(["--alias", alias])
    for show_date in dates:
        argv.extend(["--date", show_date])
    argv.extend(["--db", str(db)])
    if keep_existing:
        argv.append("--keep-existing")
    if wipe_all:
        argv.append("--wipe-all")

    original_argv = sys.argv
    try:
        sys.argv = argv
        crawler.main()
    finally:
        sys.argv = original_argv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch showtimes for all movies in one process and reuse source caches."
    )
    parser.add_argument(
        "--movie-list",
        type=Path,
        default=DEFAULT_MOVIE_LIST,
        help="Text file containing tracked movie titles.",
    )
    parser.add_argument(
        "--date",
        action="append",
        default=[],
        help="Show date. Can be repeated; defaults to today.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--keep-existing", action="store_true")
    parser.add_argument("--wipe-all", action="store_true")
    args = parser.parse_args()

    movie_list = args.movie_list if args.movie_list.is_absolute() else PROJECT_DIR / args.movie_list
    movie_titles = read_movie_titles(movie_list)
    requested_dates = list(dict.fromkeys(args.date or [date.today().isoformat()]))
    alias_map = aliases_for_titles(movie_titles)

    print("========================================")
    print("Batch movie showtime crawl")
    print("========================================")
    print(f"Movies: {len(movie_titles)}")
    print(f"Dates : {requested_dates[0]} through {requested_dates[-1]}")
    print("Mode  : shared in-process request/render/VIESHOW caches")

    for index, movie_title in enumerate(movie_titles, start=1):
        print()
        print(f"[BATCH {index}/{len(movie_titles)}] {movie_title}")
        run_movie(
            movie_title,
            dates=requested_dates,
            aliases=alias_map.get(movie_title, []),
            db=args.db,
            keep_existing=args.keep_existing,
            wipe_all=args.wipe_all,
        )

    print()
    print(f"[BATCH DONE] completed {len(movie_titles)} movie(s).")


if __name__ == "__main__":
    main()
