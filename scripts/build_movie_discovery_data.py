from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
TRACKED_MOVIES_PATH = PROJECT_DIR / "data" / "control" / "tracked_movies.json"
POSTER_CATALOG_PATH = PROJECT_DIR / "web" / "data" / "movie_posters.json"
OUTPUT_PATH = PROJECT_DIR / "web" / "data" / "movie_discovery.json"

_PUNCT_RE = re.compile(r"[\s：:!！?？〈〉《》「」『』（）()・．.、,，\-—_'\"“”‘’♪]")


def normalize_title(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().replace("臺", "台")
    return _PUNCT_RE.sub("", text)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _poster_index(poster_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    movies = poster_payload.get("movies")
    if not isinstance(movies, list):
        raise ValueError("movie_posters.movies must be a list")

    index: dict[str, dict[str, Any]] = {}
    owners: dict[str, str] = {}
    for item in movies:
        if not isinstance(item, dict):
            raise ValueError("poster catalog item must be an object")
        title = str(item.get("title") or "").strip()
        if not title:
            raise ValueError("poster catalog title must be non-empty")
        keys = [title, *(item.get("aliases") or [])]
        for raw in keys:
            key = normalize_title(raw)
            if not key:
                continue
            previous = owners.get(key)
            if previous and previous != title:
                raise ValueError(f"poster alias collision: {raw!r} -> {previous!r} / {title!r}")
            owners[key] = title
            index[key] = item
    return index


def _find_poster(movie: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for raw in [movie.get("title"), *(movie.get("aliases") or [])]:
        item = index.get(normalize_title(raw))
        if item:
            return item
    return None


def build_payload(
    tracked_payload: dict[str, Any],
    poster_payload: dict[str, Any],
) -> dict[str, Any]:
    movies = tracked_payload.get("movies")
    if not isinstance(movies, list):
        raise ValueError("tracked_movies.movies must be a list")

    index = _poster_index(poster_payload)
    output_movies: list[dict[str, Any]] = []
    missing: list[str] = []

    for movie in movies:
        if not isinstance(movie, dict) or not movie.get("is_active"):
            continue
        poster = _find_poster(movie, index)
        if not poster:
            missing.append(movie.get("title") or "")
        output_movies.append(
            {
                "id": movie.get("id"),
                "title": movie.get("title"),
                "aliases": list(movie.get("aliases") or []),
                "target_date": movie.get("target_date"),
                "poster_url": poster.get("poster_url") if poster else None,
                "poster_source": poster.get("poster_source") if poster else None,
                "poster_source_url": poster.get("poster_source_url") if poster else None,
            }
        )

    return {
        "schema_version": 1,
        "source": "data/control/tracked_movies.json + web/data/movie_posters.json",
        "source_version": tracked_payload.get("version", 0),
        "generated_at": tracked_payload.get("generated_at"),
        "lookahead_days": tracked_payload.get("lookahead_days", 7),
        "count": len(output_movies),
        "missing_poster_count": len(missing),
        "missing_posters": missing,
        "movies": output_movies,
    }


def build_and_write(
    tracked_path: Path = TRACKED_MOVIES_PATH,
    poster_path: Path = POSTER_CATALOG_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    payload = build_payload(_read_json(tracked_path), _read_json(poster_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if not output_path.exists() or output_path.read_text(encoding="utf-8") != text:
        tmp = output_path.with_suffix(output_path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(output_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the front-end movie discovery feed.")
    parser.add_argument("--require-posters", action="store_true")
    args = parser.parse_args()

    payload = build_and_write()
    print(
        f"movie discovery: {payload['count']} active movies, "
        f"{payload['missing_poster_count']} missing posters"
    )
    if args.require_posters and payload["missing_poster_count"]:
        raise SystemExit("missing poster URLs: " + ", ".join(payload["missing_posters"]))


if __name__ == "__main__":
    main()
