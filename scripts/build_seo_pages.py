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
MOVIE_LINKS_START = "<!-- SEO_MOVIE_LINKS_START -->"
MOVIE_LINKS_END = "<!-- SEO_MOVIE_LINKS_END -->"
HOME_TODAY_AI_START = "<!-- SEO_TODAY_AI_START -->"
HOME_TODAY_AI_END = "<!-- SEO_TODAY_AI_END -->"

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
    # Use a concrete root-level HTML file instead of directory-style URLs.
    # GitHub Pages serves this path without needing /dir/ -> /dir/index.html routing.
    return f"movie-{item['id']}.html"


def movie_canonical(item: dict, base_url: str) -> str:
    return urljoin(base_url, movie_href(item))


def movie_page_links(catalog: list[dict], map_data: dict) -> dict[str, str]:
    """Map each actual GeoJSON movie title to its canonical generated page."""
    map_titles = list((map_data.get("movie_features_by_date") or {}).keys())
    links: dict[str, str] = {}
    for item in catalog:
        if item.get("id") is None or not item.get("title"):
            continue
        keys = movie_keys(item)
        for map_title in map_titles:
            if normalize_title(map_title) in keys:
                links[str(map_title)] = movie_href(item)
    return links


def poster_index_from_payload(payload: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for item in payload.get("movies") or []:
        if not isinstance(item, dict):
            continue
        for value in [item.get("title"), *(item.get("aliases") or [])]:
            key = normalize_title(value)
            if key:
                index[key] = item
    return index


def archive_catalog(web_dir: Path, today: date) -> list[dict]:
    """Keep previously tracked, already-released inactive movies as stable archive URLs."""
    tracked_path = web_dir.parent / "data" / "control" / "tracked_movies.json"
    if not tracked_path.exists():
        return []

    tracked_payload = load_json(tracked_path)
    poster_path = web_dir / "data" / "movie_posters.json"
    poster_index = poster_index_from_payload(load_json(poster_path)) if poster_path.exists() else {}

    result: list[dict] = []
    for raw in tracked_payload.get("movies") or []:
        if not isinstance(raw, dict) or raw.get("is_active") is not False:
            continue
        target = parse_iso_date(raw.get("target_date"))
        # Only preserve movies that have actually reached their release date.
        # This avoids exposing disabled future drafts as indexable archive pages.
        if target is None or target > today:
            continue
        if raw.get("id") is None or not raw.get("title"):
            continue

        item = dict(raw)
        item["_archive"] = True
        poster = None
        for value in [raw.get("title"), *(raw.get("aliases") or [])]:
            poster = poster_index.get(normalize_title(value))
            if poster:
                break
        if poster:
            for key in ("poster_url", "poster_fallback_url", "poster_fit"):
                if poster.get(key):
                    item[key] = poster[key]
        result.append(item)
    return result


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


def city_sort_key(name: str) -> tuple[int, str]:
    rank = {city: index for index, city in enumerate(CITY_ORDER)}
    return (rank.get(name, 999), name)


def home_today_structured_data(
    catalog: list[dict],
    map_data: dict,
    today: date,
    base_url: str,
) -> dict:
    """Describe the product's core question: what can I watch today, and where?"""
    publisher_id = urljoin(base_url, "#publisher")
    page_id = urljoin(base_url, "#webpage")
    item_list_id = urljoin(base_url, "#today-movies")
    today_value = today.isoformat()

    list_items: list[dict] = []
    position = 1

    for item in catalog:
        if item.get("id") is None or not item.get("title"):
            continue
        target = parse_iso_date(item.get("target_date"))
        if target and target > today:
            continue

        schedules = movie_features_by_date(item, map_data)
        features = schedules.get(today_value) or []
        if not features:
            continue

        cities: set[str] = set()
        formats: set[str] = set()
        valid_times: list[str] = []
        theater_ids: set[str] = set()
        showtime_count = 0

        for feature in features:
            props = feature.get("properties") or {}
            city = str(props.get("city") or "").strip()
            if city:
                cities.add(city)
            location_id = str(props.get("location_id") or "").strip()
            location_name = str(props.get("location_name") or props.get("map_name") or "").strip()
            theater_key = location_id or normalize_title(location_name)
            if theater_key:
                theater_ids.add(theater_key)

            for showtime in props.get("showtimes") or []:
                time_value = str(showtime.get("time") or "").strip()
                if showtime_minute(time_value) is None:
                    continue
                showtime_count += 1
                valid_times.append(time_value)
                formats.update(showtime_format_tags(showtime))

        if showtime_count <= 0:
            continue

        ordered_cities = sorted(cities, key=city_sort_key)
        ordered_formats = sorted(
            formats,
            key=lambda value: (
                FORMAT_ORDER.index(value) if value in FORMAT_ORDER else 999,
                value,
            ),
        )
        earliest = min(valid_times, key=lambda value: showtime_minute(value) or 0)
        latest = max(valid_times, key=lambda value: showtime_minute(value) or 0)
        canonical = movie_canonical(item, base_url)

        summary: dict = {
            "@type": "Dataset",
            "name": f"{item['title']} {date_label(today_value)} 場次摘要",
            "temporalCoverage": today_value,
            "variableMeasured": [
                {"@type": "PropertyValue", "name": "今日場次數", "value": showtime_count},
                {"@type": "PropertyValue", "name": "上映影城數", "value": len(theater_ids)},
                {"@type": "PropertyValue", "name": "最早場次", "value": earliest},
                {"@type": "PropertyValue", "name": "最晚場次", "value": latest},
            ],
        }
        if ordered_cities:
            summary["spatialCoverage"] = [
                {"@type": "City", "name": city}
                for city in ordered_cities
            ]
        if ordered_formats:
            summary["variableMeasured"].append(
                {
                    "@type": "PropertyValue",
                    "name": "上映版本",
                    "value": "、".join(ordered_formats),
                }
            )

        movie: dict = {
            "@type": "Movie",
            "@id": canonical + "#movie",
            "name": str(item.get("title") or "").strip(),
            "url": canonical,
            "subjectOf": summary,
        }
        poster = poster_url(item, base_url)
        if poster:
            movie["image"] = poster

        list_items.append(
            {
                "@type": "ListItem",
                "position": position,
                "url": canonical,
                "item": movie,
            }
        )
        position += 1

    item_list: dict = {
        "@type": "ItemList",
        "@id": item_list_id,
        "name": f"{date_label(today_value)} 今天可看的動畫電影",
        "numberOfItems": len(list_items),
        "itemListElement": list_items,
    }
    webpage: dict = {
        "@type": "WebPage",
        "@id": page_id,
        "url": base_url,
        "name": "電影場次｜今天可以看什麼動畫電影",
        "publisher": {"@id": publisher_id},
        "mainEntity": {"@id": item_list_id},
    }
    modified = machine_update_iso(map_data)
    if modified:
        webpage["dateModified"] = modified

    return {
        "@context": "https://schema.org",
        "@graph": [
            webpage,
            {
                "@type": "Organization",
                "@id": publisher_id,
                "name": "電影場次",
                "url": base_url,
            },
            item_list,
        ],
    }


def prerender_home(
    index_path: Path,
    catalog: list[dict],
    map_data: dict,
    today: date,
    base_url: str,
) -> None:
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
    page_links_json = json.dumps(movie_page_links(catalog, map_data), ensure_ascii=False).replace("</", "<\\/")
    links_html = f"<script>window.MuseMoviePageLinks = Object.freeze({page_links_json});</script>"
    source = replace_marker_block(source, MOVIE_LINKS_START, MOVIE_LINKS_END, links_html)
    today_structured = home_today_structured_data(catalog, map_data, today, base_url)
    today_json = json.dumps(today_structured, ensure_ascii=False).replace("</", "<\\/")
    today_html = (
        '<script id="todayShowtimesStructuredData" type="application/ld+json">'
        + today_json
        + "</script>"
    )
    source = replace_marker_block(
        source,
        HOME_TODAY_AI_START,
        HOME_TODAY_AI_END,
        today_html,
    )
    index_path.write_text(source, encoding="utf-8")


def showtime_sub_label(showtime: dict) -> str:
    label = str(showtime.get("label") or "")
    time_value = str(showtime.get("time") or "")
    rest = label.replace(time_value, "", 1).strip() if time_value else label.strip()
    return rest or str(showtime.get("format") or "")


def showtime_explicit_format_tags(showtime: dict) -> list[str]:
    """Mirror the explicit whitelist matching in web/version-filter.js."""
    raw = showtime_sub_label(showtime)
    values: list[str] = []
    for name, pattern in FORMAT_RULES:
        if pattern.search(raw) and name not in values:
            values.append(name)
    if "數位" in values and "2D" in values:
        values.remove("2D")
    return values


def showtime_format_tags(showtime: dict) -> list[str]:
    """Unlabeled/unknown showtimes are treated as ordinary digital sessions."""
    values = showtime_explicit_format_tags(showtime)
    return values or ["數位"]


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


def collect_filter_values(by_date: dict[str, list[dict]]) -> tuple[list[str], list[str], list[str]]:
    cities: set[str] = set()
    formats: set[str] = set()
    chains: set[str] = set()
    for features in by_date.values():
        for feature in features:
            props = feature.get("properties") or {}
            city = str(props.get("city") or "").strip()
            chain = str(props.get("chain_name") or "").strip()
            if city:
                cities.add(city)
            if chain:
                chains.add(chain)
            for showtime in props.get("showtimes") or []:
                formats.update(showtime_format_tags(showtime))
    city_rank = {name: index for index, name in enumerate(CITY_ORDER)}
    ordered_cities = sorted(cities, key=lambda name: (city_rank.get(name, 999), name))
    format_rank = {name: index for index, name in enumerate(FORMAT_ORDER)}
    ordered_formats = sorted(formats, key=lambda name: (format_rank.get(name, 999), name))
    ordered_chains = sorted(chains, key=lambda name: name)
    return ordered_cities, ordered_formats, ordered_chains

def preferred_map_date(by_date: dict[str, list[dict]], today: date) -> str:
    values = sorted(show_date for show_date, features in by_date.items() if features)
    today_value = today.isoformat()
    if today_value in values:
        return today_value
    future = [value for value in values if value > today_value]
    if future:
        return future[0]
    return values[-1] if values else ""


def map_title_for_item(item: dict, map_data: dict) -> str:
    """Return the actual GeoJSON movie key so map restore selects the same movie."""
    title = str(item.get("title") or "").strip()
    by_title = map_data.get("movie_features_by_date") or {}
    if title in by_title:
        return title
    keys = movie_keys(item)
    for map_title in by_title:
        if normalize_title(map_title) in keys:
            return str(map_title)
    return title


def map_href(title: str, by_date: dict[str, list[dict]], today: date) -> str:
    params = {"restore": "1", "movie": title}
    show_date = preferred_map_date(by_date, today)
    if show_date:
        params["date"] = show_date
    # Explicitly navigate back to the map document. "?..." alone would keep
    # the user on movie-N.html and only change its query string.
    return "index.html?" + urlencode(params)


def parse_update_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI)


def display_update_label(map_data: dict, today: date) -> str:
    updated = parse_update_datetime(map_data.get("updated_at"))
    if updated:
        clock = updated.strftime("%H:%M")
        if updated.date() == today:
            return f"今日 {clock}"
        return f"{updated.strftime('%Y/%m/%d')} {clock}"

    source_date = parse_iso_date(map_data.get("generated_at"))
    if source_date:
        return "今日" if source_date == today else source_date.strftime("%Y/%m/%d")
    return "更新時間未提供"


def machine_update_iso(map_data: dict, item: dict | None = None) -> str:
    """Return the freshest trustworthy machine-readable modification timestamp."""
    if item and item.get("_archive"):
        archived = parse_update_datetime(item.get("updated_at"))
        if archived:
            return archived.isoformat(timespec="seconds")

    updated = parse_update_datetime(map_data.get("updated_at"))
    if updated:
        return updated.isoformat(timespec="seconds")

    generated = str(map_data.get("generated_at") or "").strip()
    if generated:
        parsed = parse_update_datetime(generated)
        if parsed:
            return parsed.isoformat(timespec="seconds")
        parsed_date = parse_iso_date(generated)
        if parsed_date:
            return parsed_date.isoformat()
    return ""


def collect_source_urls(by_date: dict[str, list[dict]]) -> list[str]:
    """Collect first-party/source URLs already carried by the canonical map data."""
    values: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str):
            url = value.strip()
            if url.startswith(("http://", "https://")) and url not in values:
                values.append(url)
        elif isinstance(value, list):
            for entry in value:
                add(entry)
        elif isinstance(value, dict):
            for entry in value.values():
                add(entry)

    for features in by_date.values():
        for feature in features:
            props = feature.get("properties") or {}
            for key in ("crawl_url", "supplemental_web_source", "official_url"):
                add(props.get(key))
    return values[:50]


def screening_start_iso(show_date: str, time_value: str) -> str:
    if parse_iso_date(show_date) is None or showtime_minute(time_value) is None:
        return ""
    return f"{show_date}T{time_value}:00+08:00"


def movie_structured_data(
    item: dict,
    by_date: dict[str, list[dict]],
    map_data: dict,
    base_url: str,
    canonical: str,
    poster: str,
) -> dict:
    """Build one JSON-LD graph for AI/search extraction without changing visible UI."""
    title = str(item.get("title") or "").strip()
    publisher_id = urljoin(base_url, "#publisher")
    webpage_id = canonical + "#webpage"
    movie_id = canonical + "#movie"

    webpage: dict = {
        "@type": "WebPage",
        "@id": webpage_id,
        "url": canonical,
        "name": f"{title} 場次",
        "publisher": {"@id": publisher_id},
        "mainEntity": {"@id": movie_id},
    }
    modified = machine_update_iso(map_data, item)
    if modified:
        webpage["dateModified"] = modified

    sources = collect_source_urls(by_date)
    if sources:
        webpage["citation"] = sources

    movie: dict = {
        "@type": "Movie",
        "@id": movie_id,
        "name": title,
        "url": canonical,
    }
    if poster:
        movie["image"] = poster

    graph: list[dict] = [
        webpage,
        {
            "@type": "Organization",
            "@id": publisher_id,
            "name": "電影場次",
            "url": base_url,
        },
        movie,
    ]

    cities: dict[str, dict] = {}
    theaters: dict[str, dict] = {}
    events: list[dict] = []

    for show_date in sorted(by_date):
        for feature_index, feature in enumerate(by_date.get(show_date) or []):
            props = feature.get("properties") or {}
            location_id = str(props.get("location_id") or "").strip()
            location_name = str(props.get("location_name") or props.get("map_name") or "影城").strip()
            stable_location = location_id or f"{feature_index}-{normalize_title(location_name)[:40]}"
            fragment = re.sub(r"[^A-Za-z0-9_-]+", "-", stable_location).strip("-") or str(feature_index)
            theater_id = f"{canonical}#cinema-{fragment}"

            if theater_id not in theaters:
                theater: dict = {
                    "@type": "MovieTheater",
                    "@id": theater_id,
                    "name": location_name,
                }
                address = str(props.get("address") or "").strip()
                city = str(props.get("city") or "").strip()
                if city:
                    normalized_city = normalize_title(city)
                    city_fragment = "-".join(
                        f"{ord(char):x}" for char in normalized_city
                    )[:96] or "unknown"
                    city_id = f"{canonical}#city-{city_fragment}"
                    if city_id not in cities:
                        cities[city_id] = {
                            "@type": "City",
                            "@id": city_id,
                            "name": city,
                            "containedInPlace": {
                                "@type": "Country",
                                "name": "台灣",
                                "identifier": "TW",
                            },
                        }
                    theater["containedInPlace"] = {"@id": city_id}
                if address or city:
                    theater["address"] = {
                        "@type": "PostalAddress",
                        "streetAddress": address,
                        "addressLocality": city,
                        "addressCountry": "TW",
                    }
                location_url = str(props.get("location_url") or "").strip()
                official_url = str(props.get("official_url") or "").strip()
                if location_url.startswith(("http://", "https://")):
                    theater["url"] = location_url
                if official_url.startswith(("http://", "https://")):
                    theater["sameAs"] = official_url
                theaters[theater_id] = theater

            showtimes = props.get("showtimes") if isinstance(props.get("showtimes"), list) else []
            for showtime_index, showtime in enumerate(showtimes):
                time_value = str(showtime.get("time") or "").strip()
                start_date = screening_start_iso(show_date, time_value)
                if not start_date:
                    continue
                tags = showtime_format_tags(showtime)
                event: dict = {
                    "@type": "ScreeningEvent",
                    "@id": f"{canonical}#screening-{fragment}-{show_date}-{time_value.replace(':', '')}-{showtime_index}",
                    "name": f"{title} {date_label(show_date)} {time_value} 場次",
                    "startDate": start_date,
                    "eventStatus": "https://schema.org/EventScheduled",
                    "location": {"@id": theater_id},
                    "workPresented": {"@id": movie_id},
                    "url": canonical,
                }
                if tags:
                    event["about"] = [{"@type": "Thing", "name": tag} for tag in tags]
                language = str(showtime.get("language") or "").strip()
                if language:
                    event["inLanguage"] = language
                booking_url = str(showtime.get("booking_url") or "").strip()
                if booking_url.startswith(("http://", "https://")):
                    event["offers"] = {
                        "@type": "Offer",
                        "url": booking_url,
                    }
                events.append(event)

    if cities:
        webpage["spatialCoverage"] = [{"@id": city_id} for city_id in cities]
    graph.extend(cities.values())
    graph.extend(theaters.values())
    graph.extend(events)
    return {"@context": "https://schema.org", "@graph": graph}


def cinema_html(feature: dict, show_date: str) -> str:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") if isinstance(geometry.get("coordinates"), list) else []
    longitude = coordinates[0] if len(coordinates) >= 2 else ""
    latitude = coordinates[1] if len(coordinates) >= 2 else ""
    name = str(props.get("map_name") or props.get("location_name") or "").strip()
    location_name = str(props.get("location_name") or name).strip()
    chain = str(props.get("chain_name") or "").strip()
    city = str(props.get("city") or "").strip()
    address = str(props.get("address") or "").strip()
    location_id = str(props.get("location_id") or "").strip()
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
        format_html = f'<p class="cinema-format">{"、".join(html.escape(value) for value in format_summary)}</p>'
    address_html = f'<p class="cinema-address">{html.escape(address)}</p>' if address else ""
    return (
        f'<article class="cinema-card" tabindex="0" '
        f'data-location-id="{html.escape(location_id, quote=True)}" '
        f'data-name="{html.escape(location_name, quote=True)}" '
        f'data-chain="{html.escape(chain, quote=True)}" '
        f'data-city="{html.escape(city, quote=True)}" '
        f'data-lat="{html.escape(str(latitude), quote=True)}" '
        f'data-long="{html.escape(str(longitude), quote=True)}">'
        '<div class="cinema-card-head">'
        f'<div><p class="cinema-chain">{html.escape(chain)}</p><h3>{html.escape(location_name)}</h3>{address_html}</div>'
        '<span class="distance-label" hidden></span>'
        '</div>'
        f'<div class="showtime-list">{"".join(showtime_html)}</div>'
        f'{format_html}'
        f'<div class="cinema-actions">{primary}{official}</div>'
        '</article>'
    )

def compact_cinema_list_html(feature: dict, show_date: str) -> str:
    props = feature.get("properties") or {}
    name = str(props.get("location_name") or props.get("map_name") or "影城").strip()
    location_id = str(props.get("location_id") or "").strip()
    showtimes = props.get("showtimes") if isinstance(props.get("showtimes"), list) else []
    parts: list[str] = []
    for showtime in showtimes:
        time_value = str(showtime.get("time") or "").strip()
        if not time_value:
            continue
        start_date = screening_start_iso(show_date, time_value)
        tags = showtime_format_tags(showtime)
        booking_url = str(showtime.get("booking_url") or "").strip()
        attrs = [
            f'datetime="{html.escape(start_date, quote=True)}"' if start_date else "",
            f'data-formats="{html.escape("|".join(tags), quote=True)}"',
            (
                f'data-booking-url="{html.escape(booking_url, quote=True)}"'
                if booking_url.startswith(("http://", "https://"))
                else ""
            ),
        ]
        attrs_text = " ".join(value for value in attrs if value)
        parts.append(
            f'<time class="cinema-list-time" {attrs_text}>{html.escape(time_value)}</time>'
        )
    return (
        f'<article class="cinema-list-card" data-location-id="{html.escape(location_id, quote=True)}">'
        f'<h3 class="cinema-list-name">{html.escape(name)}</h3>'
        f'<div class="cinema-list-times">{"".join(parts)}</div>'
        '</article>'
    )


def filter_button(value: str, label: str, data_attr: str, *, selected: bool = False) -> str:
    selected_class = " is-selected" if selected else ""
    selected_aria = "true" if selected else "false"
    return (
        f'<button type="button" class="filter-chip{selected_class}" '
        f'{data_attr}="{html.escape(value, quote=True)}" aria-pressed="{selected_aria}">'
        f'<span>{html.escape(label)}</span><strong></strong></button>'
    )


def date_chip_label(show_date: str, today: date) -> str:
    parsed = parse_iso_date(show_date)
    if not parsed:
        return show_date
    short = f"{parsed.month}/{parsed.day}"
    delta = (parsed - today).days
    if delta == 0:
        return f"今天 {short}"
    if delta == 1:
        return f"明天 {short}"
    weekday = "一二三四五六日"[parsed.weekday()]
    return f"週{weekday} {short}"


def filter_html(
    by_date: dict[str, list[dict]],
    cities: list[str],
    formats: list[str],
    chains: list[str],
    today: date,
    default_date: str,
) -> str:
    dates = sorted(show_date for show_date, features in by_date.items() if features)
    date_buttons = "".join(
        filter_button(
            show_date,
            date_chip_label(show_date, today),
            "data-filter-date",
            selected=show_date == default_date,
        )
        for show_date in dates
    )
    city_buttons = filter_button("", "全部", "data-filter-city", selected=True) + "".join(
        filter_button(city, city, "data-filter-city") for city in cities
    )
    format_buttons = filter_button("", "全部", "data-filter-format", selected=True) + "".join(
        filter_button(value, value, "data-filter-format") for value in formats
    )
    chain_buttons = filter_button("", "全部", "data-filter-chain", selected=True) + "".join(
        filter_button(value, value.replace("影城", "").strip() or value, "data-filter-chain")
        for value in chains
    )
    return f"""
<div class="filter-group">
  <span class="filter-label">日期</span>
  <div class="filter-chip-row" id="movieDateFilters">{date_buttons}</div>
</div>
<label class="movie-search">
  <span class="filter-label">搜尋影城</span>
  <input id="movieSearch" type="search" autocomplete="off" placeholder="影城、品牌、縣市" />
</label>
<div class="filter-group">
  <div class="filter-row-head">
    <span class="filter-label">時間</span>
    <button type="button" class="now-toggle is-selected" id="movieNowToggle" aria-pressed="true">現在可看</button>
  </div>
  <div class="filter-chip-row" id="moviePeriodFilters">
    <button type="button" class="filter-chip is-selected" data-filter-period="all" aria-pressed="true"><span>全天</span></button>
    <button type="button" class="filter-chip" data-filter-period="morning" aria-pressed="false"><span>上午</span></button>
    <button type="button" class="filter-chip" data-filter-period="afternoon" aria-pressed="false"><span>下午</span></button>
    <button type="button" class="filter-chip" data-filter-period="evening" aria-pressed="false"><span>晚上</span></button>
  </div>
</div>
<div class="filter-group">
  <span class="filter-label">縣市</span>
  <div class="filter-chip-row" id="movieCityFilters">{city_buttons}</div>
</div>
<div class="filter-group">
  <span class="filter-label">版本</span>
  <div class="filter-chip-row" id="movieFormatFilters">{format_buttons}</div>
</div>
<div class="filter-group">
  <span class="filter-label">影城</span>
  <div class="filter-chip-row" id="movieChainFilters">{chain_buttons}</div>
</div>
<div class="distance-row">
  <p id="distanceStatus">正在取得位置，將最近的影城排在前面…</p>
  <button id="distanceRetry" type="button">重新定位</button>
</div>
"""


def archive_page_html(item: dict, base_url: str, map_data: dict) -> str:
    title = str(item.get("title") or "").strip()
    escaped_title = html.escape(title)
    canonical = movie_canonical(item, base_url)
    poster = poster_url(item, base_url)
    target = parse_iso_date(item.get("target_date"))
    target_iso = target.isoformat() if target else ""
    target_label = target.strftime("%Y/%m/%d") if target else ""
    description = f"《{title}》上映資訊存檔。目前已無上映場次，可回到電影場次首頁查看其他正在上映與即將上映電影。"

    structured = movie_structured_data(
        item,
        {},
        map_data,
        base_url,
        canonical,
        poster,
    )

    poster_html = (
        f'<img src="{html.escape(poster, quote=True)}" alt="{escaped_title} 電影海報" '
        'style="width:min(260px,45vw);border-radius:12px;" />'
        if poster
        else ""
    )
    release_html = (
        f'<p>上映日期：<time datetime="{html.escape(target_iso, quote=True)}"><strong>{html.escape(target_label)}</strong></time></p>'
        if target
        else ""
    )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title}｜已無上映場次｜電影場次</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <meta name="robots" content="index, follow, max-image-preview:large" />
  <link rel="canonical" href="{html.escape(canonical, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="電影場次" />
  <meta property="og:title" content="{escaped_title}｜已無上映場次｜電影場次" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{html.escape(canonical, quote=True)}" />
</head>
<body style="margin:0;background:#f5f6f4;color:#1d2520;font-family:'Noto Sans TC','Microsoft JhengHei',system-ui,sans-serif;">
  <main style="width:min(760px,calc(100% - 32px));margin:0 auto;padding:32px 0 64px;">
    <a href="./" style="color:#da520d;text-decoration:none;font-weight:800;">← 電影場次</a>
    <div style="display:flex;gap:24px;align-items:flex-start;margin-top:24px;">
      {poster_html}
      <div>
        <h1 style="margin:0 0 12px;font-size:32px;">{escaped_title} 場次</h1>
        {release_html}
        <p><strong>目前已無上映場次。</strong></p>
        <p style="color:#637068;">此頁保留作為上映資訊存檔；目前場次請回首頁查看正在上映電影。</p>
      </div>
    </div>
  </main>
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\/")}</script>
</body>
</html>
"""


def movie_page_html(
    item: dict,
    by_date: dict[str, list[dict]],
    map_data: dict,
    base_url: str,
    today: date,
    page_links: dict[str, str],
) -> str:
    if item.get("_archive"):
        return archive_page_html(item, base_url, map_data)

    title = str(item.get("title") or "").strip()
    escaped_title = html.escape(title)
    canonical = movie_canonical(item, base_url)
    poster = poster_url(item, base_url)
    target_date = date_label(item.get("target_date"))
    description = (
        f"查詢《{title}》全台上映影城、日期、版本與場次時間。"
        "使用原版電影場次地圖篩選縣市、版本、影城與時間。"
    )
    update_label = display_update_label(map_data, today)
    default_date = preferred_map_date(by_date, today)
    map_title = map_title_for_item(item, map_data)

    structured = movie_structured_data(
        item,
        by_date,
        map_data,
        base_url,
        canonical,
        poster,
    )

    og_image = ""
    twitter_image = ""
    if poster:
        escaped_poster = html.escape(poster, quote=True)
        og_image = f'<meta property="og:image" content="{escaped_poster}" />'
        twitter_image = f'<meta name="twitter:image" content="{escaped_poster}" />'

    # Upcoming titles with no cinema/showtime data should not boot the map into
    # an unrelated fallback movie. Keep them as crawlable release pages.
    has_schedules = any(features for features in by_date.values())
    if not has_schedules:
        poster_html = (
            f'<img src="{html.escape(poster, quote=True)}" alt="{escaped_title} 電影海報" '
            'style="width:min(260px,45vw);border-radius:12px;" />'
            if poster
            else ""
        )
        release_date = parse_iso_date(item.get("target_date"))
        release_html = (
            f'<p>預定／上映日期：<time datetime="{release_date.isoformat()}"><strong>{html.escape(target_date)}</strong></time></p>'
            if release_date
            else ""
        )
        return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title} 場次｜電影場次</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <meta name="robots" content="index, follow, max-image-preview:large" />
  <link rel="canonical" href="{html.escape(canonical, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="電影場次" />
  <meta property="og:title" content="{escaped_title} 場次｜電影場次" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{html.escape(canonical, quote=True)}" />
  {og_image}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escaped_title} 場次｜電影場次" />
  <meta name="twitter:description" content="{html.escape(description, quote=True)}" />
  {twitter_image}
</head>
<body style="margin:0;background:#f5f6f4;color:#1d2520;font-family:'Noto Sans TC','Microsoft JhengHei',system-ui,sans-serif;">
  <main style="width:min(760px,calc(100% - 32px));margin:0 auto;padding:32px 0 64px;">
    <a href="./" style="color:#da520d;text-decoration:none;font-weight:800;">← 電影場次</a>
    <div style="display:flex;gap:24px;align-items:flex-start;margin-top:24px;">
      {poster_html}
      <div>
        <h1 style="margin:0 0 12px;font-size:32px;">{escaped_title} 場次</h1>
        {release_html}
        <p>目前沒有可查詢場次。</p>
        <p style="color:#637068;">場次資訊會隨影城公布狀況持續更新。</p>
      </div>
    </div>
  </main>
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\/")}</script>
</body>
</html>
"""

    static_sections: list[str] = []
    for show_date in sorted(by_date):
        features_for_date = by_date[show_date]
        if not features_for_date:
            continue

        city_groups: dict[str, list[dict]] = defaultdict(list)
        city_sequence: list[str] = []
        for feature in features_for_date:
            props = feature.get("properties") or {}
            city = str(props.get("city") or "").strip() or "其他地區"
            if city not in city_groups:
                city_sequence.append(city)
            city_groups[city].append(feature)

        # Preserve the map's source order for visible cards while adding semantic
        # city containers. The containers are display:contents, so UI geometry is unchanged.
        city_html: list[str] = []
        for city in city_sequence:
            cards = "".join(
                compact_cinema_list_html(feature, show_date)
                for feature in city_groups[city]
            )
            city_html.append(
                f'<section class="cinema-list-city" data-seo-city="{html.escape(city, quote=True)}">'
                f'<h3 class="seo-visually-hidden">{html.escape(city)}</h3>'
                f'{cards}</section>'
            )

        static_sections.append(
            f'<section data-seo-show-date="{html.escape(show_date, quote=True)}">'
            f'<h2 class="seo-visually-hidden"><time datetime="{html.escape(show_date, quote=True)}">'
            f'{html.escape(date_label(show_date))}</time> 場次</h2>'
            f'{"".join(city_html)}</section>'
        )
    static_list_html = "".join(static_sections)

    initial_state = {
        "restore": True,
        "movie": map_title,
        "date": default_date,
    }
    initial_state_json = json.dumps(initial_state, ensure_ascii=False).replace("</", "<\/")
    page_links_json = json.dumps(page_links, ensure_ascii=False).replace("</", "<\/")
    release_date = parse_iso_date(item.get("target_date"))
    semantic_release_html = (
        f'<p>上映日期：<time datetime="{release_date.isoformat()}">{html.escape(date_label(release_date.isoformat()))}</time></p>'
        if release_date
        else ""
    )

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{escaped_title} 場次｜電影場次</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <meta name="robots" content="index, follow, max-image-preview:large" />
  <link rel="canonical" href="{html.escape(canonical, quote=True)}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="電影場次" />
  <meta property="og:title" content="{escaped_title} 場次｜電影場次" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{html.escape(canonical, quote=True)}" />
  {og_image}
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{escaped_title} 場次｜電影場次" />
  <meta name="twitter:description" content="{html.escape(description, quote=True)}" />
  {twitter_image}
  <script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\/")}</script>
  <link
    rel="stylesheet"
    href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
    crossorigin=""
  />
  <link rel="stylesheet" href="styles.css?v=20261007a" />
  <link rel="stylesheet" href="empty-state.css?v=20260820a" />
  <link rel="stylesheet" href="movie-detail-list.css?v=20261007b" />
  <script>
    window.MuseInitialMapState = Object.freeze({initial_state_json});
    window.MuseMoviePageLinks = Object.freeze({page_links_json});
  </script>
</head>
<body>
  <main class="app-shell movie-detail-shell">
    <section class="seo-visually-hidden" aria-label="{escaped_title} 場次頁面資訊">
      <h1>{escaped_title} 場次</h1>
      {semantic_release_html}
    </section>
    <aside class="sidebar" aria-label="影城篩選">
      <div class="grabber" aria-hidden="true"></div>
      <header class="panel-head">
        <div>
          <p class="panel-title">電影場次</p>
          <p id="summaryText">載入中</p>
        </div>
      </header>

      <nav class="date-chips" id="dateChips" aria-label="選擇場次日期"></nav>

      <div class="m-seg" id="mSeg" role="tablist" aria-label="篩選分類">
        <button type="button" role="tab" data-tab="movie">電影</button>
        <button type="button" role="tab" data-tab="city">地區</button>
        <button type="button" role="tab" data-tab="time">時間</button>
        <button type="button" role="tab" data-tab="format">版本</button>
        <button type="button" role="tab" data-tab="chain">影城</button>
      </div>

      <label class="field" id="movieField">
        <span>電影</span>
        <select id="movieSelect" aria-label="選擇電影"></select>
      </label>

      <section class="m-panel" id="mMoviePanel" aria-label="選擇電影">
        <div class="filter-head"><span>電影</span></div>
        <div class="m-movie-list" id="mMovieList"></div>
      </section>

      <label class="field" id="searchField">
        <span>搜尋</span>
        <div class="search-box">
          <svg class="search-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.5" y2="16.5" />
          </svg>
          <input id="searchInput" type="search" autocomplete="off" placeholder="影城、品牌、縣市" aria-controls="searchSuggestions" />
          <button class="search-clear" id="clearSearchButton" type="button" aria-label="清除搜尋" hidden>✕</button>
        </div>
      </label>
      <div id="searchSuggestions" class="search-suggestions" hidden></div>

      <section class="m-panel" id="timeFilterPanel" aria-label="時間篩選">
        <div class="m-time-head">
          <span>現在可看場次</span>
          <span class="m-time-cap" id="timeFilterCaption">載入現在時間</span>
        </div>
        <div class="m-slider" id="timeSlider">
          <div class="m-track">
            <div class="m-fill" id="timeSliderFill"></div>
            <button class="m-knob" id="timeSliderKnob" type="button" aria-label="拖曳選擇最早場次時間">--:--</button>
          </div>
        </div>
        <div class="filter-head"><span>快速時段</span></div>
        <div class="m-period" id="timePeriodButtons">
          <button type="button" data-period="all" class="is-selected">全天</button>
          <button type="button" data-period="morning">上午</button>
          <button type="button" data-period="afternoon">下午</button>
          <button type="button" data-period="evening">晚上</button>
        </div>
      </section>

      <div class="sheet-body" id="sheetBody">
        <section class="filter-block" id="cityBlock" aria-label="縣市篩選">
          <div class="filter-head"><span>縣市</span></div>
          <div class="filter-scroll" id="cityFilterList"></div>
        </section>

        <section class="filter-block" id="formatBlock" aria-label="電影版本篩選">
          <div class="filter-head"><span>版本</span></div>
          <div class="filter-scroll" id="formatFilterList"></div>
        </section>

        <section class="filter-block" id="chainBlock" aria-label="品牌篩選">
          <div class="filter-head"><span>品牌</span></div>
          <div class="filter-scroll" id="chainFilterList"></div>
        </section>
      </div>

      <footer class="sidebar-note" aria-label="場次資訊說明">
        <p>場次資訊持續更新中</p>
        <p>實際上映與售票狀況請以影城官方資訊為準。</p>
      </footer>
    </aside>

    <section class="cinema-list-panel" id="cinemaListPanel" aria-label="{escaped_title} 影城列表">
      <header class="cinema-list-head">
        <h2>影城列表</h2>
        <strong id="cinemaListCount">0</strong>
      </header>
      <div class="cinema-list" id="cinemaList">{static_list_html}</div>
    </section>

    <section class="map-wrap" aria-label="台灣影城地圖">
      <div id="map"></div>

      <div class="m-search" id="mSearch">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.5" y2="16.5" />
        </svg>
        <input id="mSearchInput" type="search" autocomplete="off" placeholder="搜尋影城、品牌、縣市" aria-controls="mSearchSuggestions" />
        <button class="m-search-clear" id="mSearchClear" type="button" aria-label="清除搜尋" hidden>✕</button>
      </div>
      <div id="mSearchSuggestions" class="m-suggestions" hidden></div>
    </section>

    <div class="m-sheet" id="mSheet" aria-hidden="true">
      <div class="m-sheet-card" role="dialog" aria-label="影城資訊">
        <div class="m-sheet-grab" aria-hidden="true"></div>
        <button class="m-sheet-close" id="mSheetClose" type="button" aria-label="關閉">✕</button>
        <div class="m-sheet-body" id="mSheetBody"></div>
      </div>
    </div>
  </main>

  <script
    src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
    crossorigin=""
  ></script>
  <script src="runtime-config.js?v=20260903a"></script>
  <script src="carto-basemap-auth.js?v=20260903a"></script>
  <script src="time-filter.js?v=20260812a"></script>
  <script src="date-state.js?v=20260812a"></script>
  <script src="version-filter.js?v=20261007b"></script>
  <script src="movie-detail-list.js?v=20261007a"></script>
  <script src="app.js?v=20261007c"></script>
  <script src="empty-state.js?v=20260820a"></script>
</body>
</html>
"""
def write_movie_pages(
    web_dir: Path,
    active_catalog: list[dict],
    archive_items: list[dict],
    map_data: dict,
    base_url: str,
    today: date,
) -> list[str]:
    # Remove the old directory-style output and stale flat pages before rebuilding.
    movies_dir = web_dir / "movies"
    if movies_dir.exists():
        shutil.rmtree(movies_dir)
    for stale in web_dir.glob("movie-*.html"):
        stale.unlink()

    urls: list[str] = []
    catalog = [*active_catalog, *archive_items]
    page_links = movie_page_links(catalog, map_data)
    for item in catalog:
        if item.get("id") is None or not item.get("title"):
            continue
        by_date = movie_features_by_date(item, map_data)
        target = web_dir / movie_href(item)
        target.write_text(
            movie_page_html(item, by_date, map_data, base_url, today, page_links),
            encoding="utf-8",
        )
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
    agents = ("OAI-SearchBot", "PerplexityBot", "Googlebot", "Bingbot")
    blocks = [f"User-agent: {agent}\nAllow: /" for agent in agents]
    blocks.append("User-agent: *\nAllow: /")
    payload = "\n\n".join(blocks) + f"\n\nSitemap: {urljoin(base_url, 'sitemap.xml')}\n"
    (web_dir / "robots.txt").write_text(payload, encoding="utf-8")


def build(web_dir: Path, base_url: str = DEFAULT_BASE_URL, today: date | None = None) -> dict:
    base_url = base_url.rstrip("/") + "/"
    catalog_payload = load_json(web_dir / "data" / "movie_discovery.json")
    map_data = load_json(web_dir / "data" / "locations.geojson")
    catalog = [item for item in catalog_payload.get("movies", []) if isinstance(item, dict)]
    current_date = today or datetime.now(TAIPEI).date()
    archive_items = archive_catalog(web_dir, current_date)
    prerender_home(
        web_dir / "index.html",
        catalog,
        map_data,
        current_date,
        base_url,
    )
    movie_urls = write_movie_pages(
        web_dir,
        catalog,
        archive_items,
        map_data,
        base_url,
        current_date,
    )
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
