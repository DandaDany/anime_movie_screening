"""Build crawlable SEO pages from the same public data used by the map.

This runs at deploy time so the SEO landing pages, sitemap and prerendered
homepage movie links always reflect the exact GeoJSON revision being published.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

DEFAULT_BASE_URL = "https://dandadany.github.io/anime_movie_screening/"
TAIPEI = ZoneInfo("Asia/Taipei")
PUNCTUATION_RE = re.compile(r"""[\s：:!！?？〈〉《》「」『』（）()・．.、,，\-—_'"“”‘’♪]""")
NOW_START = "<!-- SEO_PRERENDER_NOW_START -->"
NOW_END = "<!-- SEO_PRERENDER_NOW_END -->"
UPCOMING_START = "<!-- SEO_PRERENDER_UPCOMING_START -->"
UPCOMING_END = "<!-- SEO_PRERENDER_UPCOMING_END -->"


def normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().replace("臺", "台")
    return PUNCTUATION_RE.sub("", text)


def parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def date_label(value: object) -> str:
    parsed = parse_iso_date(value)
    return parsed.strftime("%Y/%m/%d") if parsed else str(value or "")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def movie_keys(item: dict) -> set[str]:
    values = [item.get("title"), *(item.get("aliases") or [])]
    return {normalize_title(value) for value in values if value}


def feature_has_showtime(feature: dict) -> bool:
    props = feature.get("properties") or {}
    return bool(
        int(props.get("showtime_count") or 0) > 0
        or (isinstance(props.get("showtimes"), list) and props["showtimes"])
    )


def movie_features_by_date(item: dict, map_data: dict) -> dict[str, list[dict]]:
    keys = movie_keys(item)
    result: dict[str, list[dict]] = defaultdict(list)
    for map_title, by_date in (map_data.get("movie_features_by_date") or {}).items():
        if normalize_title(map_title) not in keys:
            continue
        for show_date, features in (by_date or {}).items():
            if not isinstance(features, list):
                continue
            result[str(show_date)].extend(feature for feature in features if feature_has_showtime(feature))
    return dict(result)


def poster_url(item: dict, base_url: str) -> str:
    value = str(item.get("poster_url") or "").strip()
    if not value:
        return ""
    return value if value.startswith(("http://", "https://")) else urljoin(base_url, value)


def movie_href(item: dict) -> str:
    return f"movies/{item['id']}/"


def movie_canonical(item: dict, base_url: str) -> str:
    return urljoin(base_url, movie_href(item))


def render_card(item: dict, kind: str) -> str:
    title = html.escape(str(item.get("title") or ""), quote=True)
    href = html.escape(movie_href(item), quote=True)
    raw_poster = str(item.get("poster_url") or "").strip()
    poster_class = "movie-card__poster"
    if item.get("poster_fit") == "contain":
        poster_class += " is-contain"
    if not raw_poster:
        poster_class += " is-missing"
    image = ""
    if raw_poster:
        loading = "eager" if kind == "now" else "lazy"
        image = (
            f'<img src="{html.escape(raw_poster, quote=True)}" alt="" '
            f'decoding="async" loading="{loading}" referrerpolicy="no-referrer" />'
        )
    return (
        f'<a class="movie-card" href="{href}" data-movie-title="{title}" data-kind="{kind}" aria-label="{title}">'
        f'<span class="{poster_class}" data-fallback="{title}">{image}</span>'
        f'<span class="movie-card__title">{title}</span>'
        "</a>"
    )


def replace_marker_block(source: str, start: str, end: str, inner: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    replacement = f"{start}\n{inner}\n{end}"
    updated, count = pattern.subn(replacement, source, count=1)
    if count != 1:
        raise RuntimeError(f"SEO marker block missing or duplicated: {start}")
    return updated


def prerender_home(index_path: Path, catalog: list[dict], map_data: dict, today: date) -> None:
    source = index_path.read_text(encoding="utf-8")
    now_items: list[dict] = []
    upcoming_items: list[dict] = []

    for item in catalog:
        target = parse_iso_date(item.get("target_date"))
        schedules = movie_features_by_date(item, map_data)
        schedule_dates = [d for d in (parse_iso_date(value) for value in schedules) if d]
        if target and target > today:
            upcoming_items.append(item)
        elif any(show_date >= today for show_date in schedule_dates):
            now_items.append(item)

    upcoming_items.sort(key=lambda item: (str(item.get("target_date") or ""), str(item.get("title") or "")))
    now_html = (
        '<div class="movie-grid" id="nowShowingGrid">'
        + "".join(render_card(item, "now") for item in now_items)
        + "</div>"
    )
    upcoming_html = (
        '<div class="movie-grid" id="comingSoonGrid">'
        + "".join(render_card(item, "upcoming") for item in upcoming_items)
        + "</div>"
    )
    source = replace_marker_block(source, NOW_START, NOW_END, now_html)
    source = replace_marker_block(source, UPCOMING_START, UPCOMING_END, upcoming_html)
    index_path.write_text(source, encoding="utf-8")


def unique_times(showtimes: list[dict]) -> list[str]:
    values: list[str] = []
    for showtime in showtimes:
        value = str(showtime.get("time") or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def unique_formats(showtimes: list[dict]) -> list[str]:
    values: list[str] = []
    for showtime in showtimes:
        parts = [
            str(showtime.get("format") or "").strip(),
            str(showtime.get("language") or "").strip(),
            str(showtime.get("auditorium") or "").strip(),
        ]
        value = " / ".join(part for part in parts if part)
        if value and value not in values:
            values.append(value)
    return values


def cinema_html(feature: dict) -> str:
    props = feature.get("properties") or {}
    name = str(props.get("map_name") or props.get("location_name") or "").strip()
    city = str(props.get("city") or "").strip()
    address = str(props.get("address") or "").strip()
    showtimes = props.get("showtimes") if isinstance(props.get("showtimes"), list) else []
    times = unique_times(showtimes)
    formats = unique_formats(showtimes)
    venue_url = str(props.get("location_url") or props.get("official_url") or "").strip()

    heading = "｜".join(part for part in (city, name) if part)
    time_html = "".join(f"<span>{html.escape(value)}</span>" for value in times)
    format_html = ""
    if formats:
        format_html = f'<p class="cinema-format">版本／影廳：{html.escape("、".join(formats))}</p>'
    address_html = f'<p class="cinema-address">{html.escape(address)}</p>' if address else ""
    link_html = ""
    if venue_url:
        link_html = (
            f'<a class="cinema-link" href="{html.escape(venue_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">影城資訊</a>'
        )
    return (
        '<article class="cinema-card">'
        f"<h3>{html.escape(heading)}</h3>"
        f"{address_html}"
        f'<p class="showtime-list">{time_html}</p>'
        f"{format_html}{link_html}"
        "</article>"
    )


def movie_page_html(item: dict, by_date: dict[str, list[dict]], map_data: dict, base_url: str) -> str:
    title = str(item.get("title") or "").strip()
    escaped_title = html.escape(title)
    canonical = movie_canonical(item, base_url)
    poster = poster_url(item, base_url)
    target_date = date_label(item.get("target_date"))
    description = f"查詢《{title}》全台上映影城、日期、版本與場次時間。場次持續更新，實際上映與售票狀況請以影城官方資訊為準。"
    updated_at = str(map_data.get("updated_at") or map_data.get("generated_at") or "").strip()

    schedule_sections: list[str] = []
    for show_date in sorted(by_date):
        features = sorted(
            by_date[show_date],
            key=lambda feature: (
                str((feature.get("properties") or {}).get("city") or ""),
                str((feature.get("properties") or {}).get("map_name") or ""),
            ),
        )
        if not features:
            continue
        cards = "".join(cinema_html(feature) for feature in features)
        schedule_sections.append(
            f'<section class="schedule-day"><h2>{html.escape(date_label(show_date))} 場次</h2>'
            f'<div class="cinema-list">{cards}</div></section>'
        )

    if schedule_sections:
        schedules_html = "".join(schedule_sections)
    else:
        schedules_html = (
            '<section class="schedule-empty"><h2>目前沒有可查詢場次</h2>'
            '<p>上映資訊會隨影城公布狀況持續更新，你仍可回到電影地圖查看其他電影。</p></section>'
        )

    poster_html = ""
    if poster:
        poster_html = f'<img class="movie-poster" src="{html.escape(poster, quote=True)}" alt="{escaped_title} 電影海報" />'

    release_html = f"<p>預定／上映日期：<strong>{html.escape(target_date)}</strong></p>" if target_date else ""
    updated_html = f"<p>場次資料更新：{html.escape(updated_at)}</p>" if updated_at else ""

    structured = {
        "@context": "https://schema.org",
        "@type": "Movie",
        "name": title,
        "url": canonical,
    }
    if poster:
        structured["image"] = poster

    og_image = ""
    twitter_image = ""
    if poster:
        escaped_poster = html.escape(poster, quote=True)
        og_image = f'<meta property="og:image" content="{escaped_poster}" />'
        twitter_image = f'<meta name="twitter:image" content="{escaped_poster}" />'

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title} 場次｜全台動畫電影上映地圖</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <link rel="canonical" href="{html.escape(canonical, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="全台動畫電影上映地圖" />
  <meta property="og:title" content="{escaped_title} 場次｜全台動畫電影上映地圖" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{html.escape(canonical, quote=True)}" />
  {og_image}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escaped_title} 場次｜全台動畫電影上映地圖" />
  <meta name="twitter:description" content="{html.escape(description, quote=True)}" />
  {twitter_image}
  <link rel="stylesheet" href="../../seo.css" />
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\/")}</script>
</head>
<body>
  <header class="site-head">
    <a href="../../">← 回到動畫電影地圖</a>
  </header>
  <main class="movie-page">
    <section class="movie-hero">
      {poster_html}
      <div>
        <p class="eyebrow">全台動畫電影場次</p>
        <h1>{escaped_title}</h1>
        {release_html}
        {updated_html}
        <a class="map-cta" href="../../?restore=1">在地圖查看影城位置</a>
      </div>
    </section>
    {schedules_html}
    <p class="disclaimer">場次資訊持續更新中，實際上映與售票狀況請以影城官方資訊為準。</p>
  </main>
</body>
</html>
"""


def write_movie_pages(web_dir: Path, catalog: list[dict], map_data: dict, base_url: str) -> list[str]:
    movies_dir = web_dir / "movies"
    if movies_dir.exists():
        shutil.rmtree(movies_dir)
    urls: list[str] = []
    for item in catalog:
        if item.get("id") is None or not item.get("title"):
            continue
        by_date = movie_features_by_date(item, map_data)
        target = movies_dir / str(item["id"]) / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(movie_page_html(item, by_date, map_data, base_url), encoding="utf-8")
        urls.append(movie_canonical(item, base_url))
    return urls


def write_sitemap(web_dir: Path, urls: list[str], map_data: dict, base_url: str) -> None:
    lastmod = str(map_data.get("updated_at") or map_data.get("generated_at") or "")[:10]
    all_urls = [base_url, *urls]
    entries = []
    for url in all_urls:
        lastmod_xml = f"<lastmod>{xml_escape(lastmod)}</lastmod>" if lastmod else ""
        entries.append(f"<url><loc>{xml_escape(url)}</loc>{lastmod_xml}</url>")
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    (web_dir / "sitemap.xml").write_text(payload, encoding="utf-8")


def write_robots(web_dir: Path, base_url: str) -> None:
    payload = f"User-agent: *\nAllow: /\n\nSitemap: {urljoin(base_url, 'sitemap.xml')}\n"
    (web_dir / "robots.txt").write_text(payload, encoding="utf-8")


def build(web_dir: Path, base_url: str = DEFAULT_BASE_URL, today: date | None = None) -> dict:
    base_url = base_url.rstrip("/") + "/"
    catalog_payload = load_json(web_dir / "data" / "movie_discovery.json")
    map_data = load_json(web_dir / "data" / "locations.geojson")
    catalog = [item for item in catalog_payload.get("movies", []) if isinstance(item, dict)]
    current_date = today or datetime.now(TAIPEI).date()

    prerender_home(web_dir / "index.html", catalog, map_data, current_date)
    movie_urls = write_movie_pages(web_dir, catalog, map_data, base_url)
    write_sitemap(web_dir, movie_urls, map_data, base_url)
    write_robots(web_dir, base_url)

    return {
        "movies": len(movie_urls),
        "sitemap_urls": len(movie_urls) + 1,
        "base_url": base_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static SEO landing pages for the movie map.")
    parser.add_argument("--web-dir", type=Path, default=Path(__file__).resolve().parents[1] / "web")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--today", help="Override Asia/Taipei current date for deterministic testing.")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    result = build(args.web_dir, args.base_url, today)
    print(
        f"SEO build complete: movies={result['movies']} "
        f"sitemap_urls={result['sitemap_urls']} base={result['base_url']}"
    )


if __name__ == "__main__":
    main()
