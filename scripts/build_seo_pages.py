"""Build crawlable movie landing pages from the same public data used by the map."""

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
from urllib.parse import urlencode, urljoin
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

DEFAULT_BASE_URL = "https://dandadany.github.io/anime_movie_screening/"
TAIPEI = ZoneInfo("Asia/Taipei")
PUNCTUATION_RE = re.compile(r"""[\s：:!！?？〈〉《》「」『』（）()・．.、,，\-—_'"“”‘’♪]""")
NOW_START = "<!-- SEO_PRERENDER_NOW_START -->"
NOW_END = "<!-- SEO_PRERENDER_NOW_END -->"
UPCOMING_START = "<!-- SEO_PRERENDER_UPCOMING_START -->"
UPCOMING_END = "<!-- SEO_PRERENDER_UPCOMING_END -->"

FORMAT_RULES = [
    ("IMAX", re.compile(r"imax", re.I)),
    ("4DX", re.compile(r"4dx", re.I)),
    ("4D+", re.compile(r"4d\+", re.I)),
    ("MX4D", re.compile(r"mx-?4d", re.I)),
    ("ScreenX", re.compile(r"screen\s*-?\s*x", re.I)),
    ("TITAN", re.compile(r"titan", re.I)),
    ("ULTRA", re.compile(r"ultra", re.I)),
    ("LUXE", re.compile(r"luxe", re.I)),
    ("Dolby", re.compile(r"dolby|\bdva\b", re.I)),
    ("ATMOS", re.compile(r"atmos", re.I)),
    ("INFINITY VISION", re.compile(r"infinity\s*vision", re.I)),
    ("HFR", re.compile(r"\bhfr\b", re.I)),
    ("REMMI", re.compile(r"remmi", re.I)),
    ("GC", re.compile(r"\bgc\b|gold\s*class", re.I)),
    ("MUCROWN", re.compile(r"mucrown", re.I)),
    ("A+", re.compile(r"a\+", re.I)),
    ("皇家廳", re.compile(r"皇家廳")),
    ("COACH廳", re.compile(r"coach廳", re.I)),
    ("BOOM廳", re.compile(r"boom廳", re.I)),
    ("Pink Sofa", re.compile(r"pink\s*sofa", re.I)),
    ("VIP", re.compile(r"\bvip\b", re.I)),
    ("水影威尼斯", re.compile(r"水影威尼斯")),
    ("V廳", re.compile(r"v[-\s]?hall|v廳", re.I)),
    ("FreeLaxx", re.compile(r"free\s*laxx|跨腳廳", re.I)),
    ("跨電癮", re.compile(r"跨電癮")),
    ("KIDS+", re.compile(r"kids\+?|親子", re.I)),
    ("XL", re.compile(r"\bxl\b", re.I)),
    ("巨幕", re.compile(r"巨幕")),
    ("3D", re.compile(r"3d", re.I)),
    ("數位", re.compile(r"數位")),
    ("2D", re.compile(r"2d", re.I)),
]
FORMAT_ORDER = [name for name, _ in FORMAT_RULES]
CITY_ORDER = [
    "基隆市", "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
    "臺中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣",
    "臺南市", "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣",
    "澎湖縣", "金門縣", "連江縣",
]
DIRECT_BOOKING_PATTERNS = [
    re.compile(r"vscinemas\.com\.tw/vsTicketing/ticketing/booking\.aspx.*[?&]txtSessionId=", re.I),
    re.compile(r"miramarcinemas\.tw/Booking/TicketType\?.*[?&]session=", re.I),
    re.compile(r"showtimes\.com\.tw/ticketing/selectEvents/\d+/\d+\?[^#]*[?&]?date=\d{4}-\d{2}-\d{2}", re.I),
    re.compile(r"mldcinema\.com\.tw/OnlinePurchase\.php\?[^#]*[?&]?computerid=\d+", re.I),
    re.compile(r"broadway-cineplex\.com\.tw/book\.html\?(?=[^#]*\bobj=)(?=[^#]*[?&]v(?:=)?[\w-]+)[^#]+", re.I),
    re.compile(r"ezding\.com\.tw/cinemabooking\?(?=[^#]*\bcinemaid=)[^#]+", re.I),
]


def normalize_title(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().replace("臺", "台")
    return PUNCTUATION_RE.sub("", text)


def parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
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
    now_html = '<div class="movie-grid" id="nowShowingGrid">' + "".join(render_card(item, "now") for item in now_items) + "</div>"
    upcoming_html = '<div class="movie-grid" id="comingSoonGrid">' + "".join(render_card(item, "upcoming") for item in upcoming_items) + "</div>"
    source = replace_marker_block(source, NOW_START, NOW_END, now_html)
    source = replace_marker_block(source, UPCOMING_START, UPCOMING_END, upcoming_html)
    index_path.write_text(source, encoding="utf-8")


def showtime_sub_label(showtime: dict) -> str:
    label = str(showtime.get("label") or "")
    time_value = str(showtime.get("time") or "")
    rest = label.replace(time_value, "", 1).strip() if time_value else label.strip()
    return rest or str(showtime.get("format") or "")


def showtime_format_tags(showtime: dict) -> list[str]:
    raw = showtime_sub_label(showtime)
    values: list[str] = []
    for name, pattern in FORMAT_RULES:
        if pattern.search(raw) and name not in values:
            values.append(name)
    if "數位" in values and "2D" in values:
        values.remove("2D")
    if not values:
        fallback = str(showtime.get("format") or "").strip()
        if fallback:
            values.append(fallback)
    return values


def direct_showtime_booking_url(showtime: dict) -> str:
    value = str(showtime.get("booking_url") or "").strip()
    if not value:
        return ""
    return value if any(pattern.search(value) for pattern in DIRECT_BOOKING_PATTERNS) else ""


def showtime_minute(value: object) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", str(value or "").strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def collect_filter_values(by_date: dict[str, list[dict]]) -> tuple[list[str], list[str]]:
    cities: set[str] = set()
    formats: set[str] = set()
    for features in by_date.values():
        for feature in features:
            props = feature.get("properties") or {}
            city = str(props.get("city") or "").strip()
            if city:
                cities.add(city)
            for showtime in props.get("showtimes") or []:
                formats.update(showtime_format_tags(showtime))
    city_rank = {name: index for index, name in enumerate(CITY_ORDER)}
    ordered_cities = sorted(cities, key=lambda name: (city_rank.get(name, 999), name))
    format_rank = {name: index for index, name in enumerate(FORMAT_ORDER)}
    ordered_formats = sorted(formats, key=lambda name: (format_rank.get(name, 999), name))
    return ordered_cities, ordered_formats


def preferred_map_date(by_date: dict[str, list[dict]], today: date) -> str:
    values = sorted(show_date for show_date, features in by_date.items() if features)
    today_value = today.isoformat()
    if today_value in values:
        return today_value
    future = [value for value in values if value > today_value]
    if future:
        return future[0]
    return values[-1] if values else ""


def map_href(title: str, by_date: dict[str, list[dict]], today: date) -> str:
    params = {"restore": "1", "movie": title}
    show_date = preferred_map_date(by_date, today)
    if show_date:
        params["date"] = show_date
    return "../../?" + urlencode(params)


def display_update_label(map_data: dict, today: date) -> str:
    source_date = parse_iso_date(map_data.get("updated_at") or map_data.get("generated_at"))
    if source_date == today:
        return "今日 8:00"
    if source_date:
        return f"{source_date.strftime('%Y/%m/%d')} 8:00"
    return "每日 8:00"


def cinema_html(feature: dict, show_date: str) -> str:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") if isinstance(geometry.get("coordinates"), list) else []
    longitude = coordinates[0] if len(coordinates) >= 2 else ""
    latitude = coordinates[1] if len(coordinates) >= 2 else ""
    name = str(props.get("map_name") or props.get("location_name") or "").strip()
    city = str(props.get("city") or "").strip()
    address = str(props.get("address") or "").strip()
    showtimes = props.get("showtimes") if isinstance(props.get("showtimes"), list) else []
    location_url = str(props.get("location_url") or "").strip()
    official_url = str(props.get("official_url") or "").strip()

    showtime_html: list[str] = []
    has_direct_booking = False
    format_summary: list[str] = []
    for showtime in showtimes:
        time_value = str(showtime.get("time") or "").strip()
        if not time_value:
            continue
        tags = showtime_format_tags(showtime)
        for tag in tags:
            if tag not in format_summary:
                format_summary.append(tag)
        direct_url = direct_showtime_booking_url(showtime)
        has_direct_booking = has_direct_booking or bool(direct_url)
        attrs = (
            f'data-show-date="{html.escape(show_date, quote=True)}" '
            f'data-minute="{showtime_minute(time_value) if showtime_minute(time_value) is not None else ""}" '
            f'data-formats="{html.escape("|".join(tags), quote=True)}"'
        )
        label = html.escape(time_value)
        if tags:
            label += f'<small>{html.escape(" ".join(tags[:3]))}</small>'
        if direct_url:
            showtime_html.append(
                f'<button type="button" class="showtime-chip is-bookable" {attrs} '
                f'data-booking-url="{html.escape(direct_url, quote=True)}" aria-pressed="false">{label}</button>'
            )
        else:
            showtime_html.append(f'<span class="showtime-chip" {attrs}>{label}</span>')

    primary = ""
    if has_direct_booking:
        primary = (
            '<a class="cinema-action cinema-action-primary is-disabled" data-booking-cta '
            'aria-disabled="true"><span data-booking-label>前往訂票</span></a>'
        )
    elif location_url:
        primary = (
            f'<a class="cinema-action cinema-action-primary" href="{html.escape(location_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">場次入口</a>'
        )
    official = ""
    if official_url:
        official = (
            f'<a class="cinema-action cinema-action-secondary" href="{html.escape(official_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">官方網站</a>'
        )

    format_html = ""
    if format_summary:
        format_html = f'<p class="cinema-format">版本／影廳：{html.escape("、".join(format_summary))}</p>'
    address_html = f'<p class="cinema-address">{html.escape(address)}</p>' if address else ""
    lat_attr = html.escape(str(latitude), quote=True)
    long_attr = html.escape(str(longitude), quote=True)
    return (
        f'<article class="cinema-card" data-city="{html.escape(city, quote=True)}" '
        f'data-lat="{lat_attr}" data-long="{long_attr}">'
        '<div class="cinema-card-head">'
        f'<div><h3>{html.escape(name)}</h3>{address_html}</div>'
        '<span class="distance-label" hidden></span>'
        '</div>'
        f'<div class="showtime-list">{"".join(showtime_html)}</div>'
        f'{format_html}'
        f'<div class="cinema-actions">{primary}{official}</div>'
        '</article>'
    )


def filter_html(cities: list[str], formats: list[str]) -> str:
    city_options = "".join(
        f'<option value="{html.escape(city, quote=True)}">{html.escape(city)}</option>' for city in cities
    )
    format_options = "".join(
        f'<option value="{html.escape(value, quote=True)}">{html.escape(value)}</option>' for value in formats
    )
    return f"""
<section class="showtime-tools" aria-label="場次篩選">
  <div class="showtime-filter-grid">
    <label>縣市
      <select id="movieFilterCity">
        <option value="">全部縣市</option>
        {city_options}
      </select>
    </label>
    <label>版本
      <select id="movieFilterFormat">
        <option value="">全部版本</option>
        {format_options}
      </select>
    </label>
    <label>時間
      <select id="movieFilterTime">
        <option value="all">全天</option>
        <option value="now">現在可看</option>
        <option value="morning">上午</option>
        <option value="afternoon">下午</option>
        <option value="evening">晚上</option>
      </select>
    </label>
  </div>
  <div class="distance-row">
    <p id="distanceStatus">正在取得位置，將最近的影城排在前面…</p>
    <button id="distanceRetry" type="button">重新定位</button>
  </div>
</section>
<p class="filter-empty" id="filterEmpty" hidden>目前沒有符合篩選條件的場次。</p>
"""


def movie_page_html(
    item: dict,
    by_date: dict[str, list[dict]],
    map_data: dict,
    base_url: str,
    today: date,
) -> str:
    title = str(item.get("title") or "").strip()
    escaped_title = html.escape(title)
    canonical = movie_canonical(item, base_url)
    poster = poster_url(item, base_url)
    target_date = date_label(item.get("target_date"))
    description = f"查詢《{title}》全台上映影城、日期、版本與場次時間。場次持續更新，實際上映與售票狀況請以影城官方資訊為準。"
    update_label = display_update_label(map_data, today)
    cities, formats = collect_filter_values(by_date)

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
        cards = "".join(cinema_html(feature, show_date) for feature in features)
        schedule_sections.append(
            f'<section class="schedule-day" data-show-date="{html.escape(show_date, quote=True)}">'
            f'<h2>{html.escape(date_label(show_date))} 場次</h2>'
            f'<div class="cinema-list">{cards}</div></section>'
        )

    schedules_html = "".join(schedule_sections)
    if not schedules_html:
        schedules_html = (
            '<section class="schedule-empty"><h2>目前沒有可查詢場次</h2>'
            '<p>上映資訊會隨影城公布狀況持續更新，你仍可回到電影地圖查看其他電影。</p></section>'
        )

    poster_html = (
        f'<img class="movie-poster" src="{html.escape(poster, quote=True)}" alt="{escaped_title} 電影海報" />'
        if poster else ""
    )
    release_html = f"<p>預定／上映日期：<strong>{html.escape(target_date)}</strong></p>" if target_date else ""
    map_link = html.escape(map_href(title, by_date, today), quote=True)

    structured = {"@context": "https://schema.org", "@type": "Movie", "name": title, "url": canonical}
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
  <link rel="stylesheet" href="../../seo.css?v=20261006b" />
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\/")}</script>
  <script src="../../seo-movie.js?v=20261006b" defer></script>
</head>
<body>
  <header class="site-head">
    <a href="../../">← 回到動畫電影首頁</a>
  </header>
  <main class="movie-page">
    <section class="movie-hero">
      {poster_html}
      <div>
        <p class="eyebrow">全台動畫電影場次</p>
        <h1>{escaped_title}</h1>
        {release_html}
        <p>場次資料更新：<strong>{html.escape(update_label)}</strong></p>
        <a class="map-cta" href="{map_link}">在地圖查看影城位置</a>
      </div>
    </section>
    {filter_html(cities, formats) if schedule_sections else ""}
    {schedules_html}
    <p class="disclaimer">場次資訊持續更新中，實際上映與售票狀況請以影城官方資訊為準。</p>
  </main>
</body>
</html>
"""


def write_movie_pages(web_dir: Path, catalog: list[dict], map_data: dict, base_url: str, today: date) -> list[str]:
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
        target.write_text(movie_page_html(item, by_date, map_data, base_url, today), encoding="utf-8")
        urls.append(movie_canonical(item, base_url))
    return urls


def write_sitemap(web_dir: Path, urls: list[str], map_data: dict, base_url: str) -> None:
    lastmod = str(map_data.get("updated_at") or map_data.get("generated_at") or "")[:10]
    entries = []
    for url in [base_url, *urls]:
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
    movie_urls = write_movie_pages(web_dir, catalog, map_data, base_url, current_date)
    write_sitemap(web_dir, movie_urls, map_data, base_url)
    write_robots(web_dir, base_url)
    return {"movies": len(movie_urls), "sitemap_urls": len(movie_urls) + 1, "base_url": base_url}


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
