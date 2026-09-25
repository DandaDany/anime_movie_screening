#!/usr/bin/env python3
"""Live audit of special-format extraction for seven non-primary cinema sources.

Research only. For each official source this script compares:
1) special-format text visible in the live source;
2) what the current fetcher would preserve in format/auditorium;
3) whether the current frontend FORMAT_RULES would recognize the preserved text.

No writes, logins, booking actions, or reservations.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import defaultdict

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from fetch_movie_showtimes import (
    HALAR_URL,
    LUNA_URL,
    LUX_URL,
    MIRAMAR_URL,
    MLD_URL,
    VENICE_URL,
    WINDLION_URL,
    normalize_show_date,
    render_page_html,
    request_bytes,
    text_blocks_from_html,
)

SPECIAL_PATTERNS = [
    ("IMAX", re.compile(r"\bIMAX\b", re.I)),
    ("4DX", re.compile(r"\b4DX\b", re.I)),
    ("4D+", re.compile(r"(?<![A-Z0-9])4D\+(?![A-Z0-9])", re.I)),
    ("Dolby", re.compile(r"\bDolby\b", re.I)),
    ("ATMOS", re.compile(r"\bAtmos\b", re.I)),
    ("INFINITY VISION", re.compile(r"Infinity\s*Vision", re.I)),
    ("XL", re.compile(r"(?<![A-Z0-9])XL(?![A-Z0-9])", re.I)),
    ("HFR", re.compile(r"\bHFR\b", re.I)),
    ("3D", re.compile(r"\b3D\b", re.I)),
    ("VIP", re.compile(r"\bVIP\b", re.I)),
    ("V廳", re.compile(r"V\s*廳", re.I)),
    ("FreeLaxx", re.compile(r"Free\s*Laxx", re.I)),
    ("KIDS+", re.compile(r"KIDS\+", re.I)),
    ("巨幕", re.compile(r"巨幕")),
    ("MUCROWN", re.compile(r"MUCROWN", re.I)),
    ("TITAN", re.compile(r"TITAN", re.I)),
    ("LUXE", re.compile(r"LUXE", re.I)),
    ("MX4D", re.compile(r"MX-?4D", re.I)),
    ("ScreenX", re.compile(r"Screen\s*-?\s*X", re.I)),
]

# Current web/app.js FORMAT_RULES names/patterns, mirrored only for the audit.
CURRENT_FRONTEND_PATTERNS = [
    ("IMAX", re.compile(r"imax", re.I)),
    ("4DX", re.compile(r"4dx", re.I)),
    ("MX4D", re.compile(r"mx-?4d", re.I)),
    ("ScreenX", re.compile(r"screen\s*-?\s*x", re.I)),
    ("巨幕", re.compile(r"巨幕")),
    ("TITAN", re.compile(r"titan", re.I)),
    ("ULTRA", re.compile(r"ultra", re.I)),
    ("LUXE", re.compile(r"luxe", re.I)),
    ("Dolby", re.compile(r"dolby|\bdva\b", re.I)),
    ("ATMOS", re.compile(r"atmos", re.I)),
    ("GC", re.compile(r"\bgc\b|gold\s*class", re.I)),
    ("MUCROWN", re.compile(r"mucrown", re.I)),
    ("A+", re.compile(r"a\+", re.I)),
    ("皇家廳", re.compile(r"皇家廳")),
    ("COACH廳", re.compile(r"coach廳", re.I)),
    ("BOOM廳", re.compile(r"boom廳", re.I)),
    ("Pink Sofa", re.compile(r"pink\s*sofa", re.I)),
    ("VIP", re.compile(r"\bvip\b", re.I)),
    ("3D", re.compile(r"3d", re.I)),
    ("數位", re.compile(r"數位")),
    ("2D", re.compile(r"2d", re.I)),
]


def specials(text: str | None) -> list[str]:
    raw = text or ""
    return [name for name, pattern in SPECIAL_PATTERNS if pattern.search(raw)]


def frontend_tags(text: str | None) -> list[str]:
    raw = text or ""
    return [name for name, pattern in CURRENT_FRONTEND_PATTERNS if pattern.search(raw)]


def one_line(text: str | None, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    return value[:limit]


def rec(source: str, *, title="", date="", time="", fmt="", auditorium="", raw="") -> dict:
    label = " / ".join(value for value in [fmt, auditorium] if value)
    return {
        "source": source,
        "title": one_line(title, 160),
        "date": one_line(date, 40),
        "time": one_line(time, 20),
        "format": one_line(fmt, 180),
        "auditorium": one_line(auditorium, 180),
        "raw": one_line(raw),
        "source_specials": specials(raw),
        "preserved_specials": specials(label),
        "frontend_tags": frontend_tags(label),
    }


def audit_miramar() -> tuple[list[dict], list[str]]:
    raw = request_bytes(MIRAMAR_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records = []
    source_hits = []
    for movie in soup.select(".timetable_list"):
        title = one_line(movie.select_one(".movie_info .title").get_text(" ", strip=True) if movie.select_one(".movie_info .title") else "")
        if specials(movie.get_text(" ", strip=True)):
            source_hits.append(one_line(movie.get_text(" ", strip=True), 500))
        for block in movie.select(".time_list_right > .block"):
            classes = " ".join(block.get("class", []))
            room_node = block.select_one(".room")
            room = one_line(room_node.get_text(" ", strip=True).replace("watch_later", "").strip() if room_node else "")
            raw_text = f"{title} | {classes} | {room}"
            for time_link in block.select("a.booking_time"):
                records.append(rec("美麗華", title=title, date=classes, time=time_link.get_text(strip=True), fmt=room, raw=raw_text))
    return records, source_hits


def audit_lux() -> tuple[list[dict], list[str]]:
    raw = request_bytes(LUX_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records = []
    source_hits = []
    for movie in soup.select(".movie_list_box"):
        title_node = movie.select_one("h1")
        title = one_line(title_node.get_text(" ", strip=True).replace("立即訂票", "").strip() if title_node else "")
        movie_text = movie.get_text(" ", strip=True)
        if specials(movie_text):
            source_hits.append(one_line(movie_text, 500))
        for date_node in movie.select("h3"):
            date_text = one_line(date_node.get_text(" ", strip=True))
            times_node = date_node.find_next_sibling("ul")
            if not times_node:
                continue
            for item in times_node.select("li"):
                item_text = one_line(item.get_text(" ", strip=True))
                match = re.search(r"(\d{1,2}:\d{2})(?:\s*\|\s*([A-Za-z0-9]+))?", item_text)
                if not match:
                    continue
                auditorium = match.group(2) or ""
                records.append(rec("樂聲", title=title, date=date_text, time=match.group(1), fmt=title, auditorium=auditorium, raw=f"{title} | {date_text} | {item_text}"))
    return records, source_hits


def audit_venice() -> tuple[list[dict], list[str]]:
    records = []
    source_hits = []
    for page_number in range(1, 5):
        url = VENICE_URL.format(page=page_number)
        try:
            html = render_page_html(url, wait_ms=4000)
        except Exception as exc:
            source_hits.append(f"page {page_number} ERROR {type(exc).__name__}: {exc}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        lines = [one_line(x) for x in soup.get_text("\n", strip=True).splitlines() if one_line(x)]
        for line in lines:
            if specials(line):
                source_hits.append(line)
        # Mirror the generic parser at field level: any movie/title-like line
        # containing a special token becomes format; hall is only recognized by
        # the current generic hall regex.
        for i, line in enumerate(lines):
            if not specials(line):
                continue
            nearby = "\n".join(lines[max(0, i - 8):i + 9])
            times = re.findall(r"\b\d{1,2}:\d{2}\b", nearby)
            hall_match = re.search(r"([A-Za-z]?\d+\s*廳|[A-Za-z]+廳|BOOM\s*廳|LUXE\s*\d*廳|IMAX\s*廳|MX4D\s*廳)", nearby)
            auditorium = hall_match.group(1).replace(" ", "") if hall_match else ""
            for start in times[:8]:
                records.append(rec("威尼斯", title=line, time=start.zfill(5), fmt=line, auditorium=auditorium, raw=nearby))
    return records, source_hits


def audit_windlion() -> tuple[list[dict], list[str]]:
    html = render_page_html(f"{WINDLION_URL}#anchor", wait_ms=6000)
    lines = text_blocks_from_html(html)
    records = []
    source_hits = [one_line(line) for line in lines if specials(line)]
    current_title = ""
    current_language = ""
    current_date = ""
    for line in lines:
        if re.match(r"\d{4}-\d{2}-\d{2}", line):
            current_date = line[:10]
            continue
        if line.startswith("語言"):
            current_language = line.replace("語言", "").replace(":", "").strip()
            continue
        match = re.search(r"(\d{1,2}:\d{2})\(([^)]+)\)", line)
        if match:
            fmt = " ".join(value for value in [current_title, current_language] if value)
            records.append(rec("金獅", title=current_title, date=current_date, time=match.group(1), fmt=fmt, auditorium=match.group(2), raw=f"{current_title} | {current_language} | {line}"))
            continue
        # The production parser sets current_title only after movie_matches.
        # For source-wide audit, a non-structural line before its sessions is
        # the closest equivalent movie/title candidate.
        if line and not re.match(r"^(語言|\d{4}-\d{2}-\d{2})", line) and not re.search(r"\d{1,2}:\d{2}", line):
            current_title = one_line(line, 180)
            current_language = ""
    return records, source_hits


def audit_mld() -> tuple[list[dict], list[str]]:
    raw = request_bytes(MLD_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records = []
    source_hits = []
    for movie in soup.select(".timesList .showingBox"):
        title_node = movie.select_one(".photoBox .title")
        title = one_line(title_node.get_text(" ", strip=True) if title_node else "")
        movie_text = movie.get_text(" ", strip=True)
        if specials(movie_text):
            source_hits.append(one_line(movie_text, 500))
        for day in movie.select(".dateBox .item dl"):
            date_node = day.find("dt")
            date_text = one_line(date_node.get_text(" ", strip=True) if date_node else "")
            for time_link in day.select("dd a"):
                time = one_line(time_link.get_text(strip=True))
                if re.fullmatch(r"\d{1,2}:\d{2}", time):
                    records.append(rec("台鋁", title=title, date=date_text, time=time, fmt=title, raw=f"{title} | {date_text} | {time}"))
    return records, source_hits


def audit_luna() -> tuple[list[dict], list[str]]:
    raw = request_bytes(LUNA_URL, headers={"Referer": "https://www.lunacinemax.com.tw/"})
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records = []
    page_text = soup.get_text(" ", strip=True)
    source_hits = [one_line(line) for line in soup.get_text("\n", strip=True).splitlines() if specials(line)]
    for date_node in soup.select("span[id$='SHOW_DATELabel']"):
        date_text = one_line(date_node.get_text(" ", strip=True))
        date_container = date_node.find_parent("td")
        if not date_container:
            continue
        for title_node in date_container.select("span[id$='NAME_CHTLabel']"):
            title = one_line(title_node.get_text(" ", strip=True))
            movie_table = title_node.find_parent("table")
            movie_row = movie_table.find_parent("tr") if movie_table else None
            screen_table = movie_row.find_parent("table") if movie_row else None
            screen_row = screen_table.find_parent("tr") if screen_table else None
            hall_node = screen_row.select_one("span[id$='SCREEN_NAMELabel']") if screen_row else None
            auditorium = one_line(hall_node.get_text(" ", strip=True) if hall_node else "")
            for time_node in movie_table.select("span[id$='TIMELabel']") if movie_table else []:
                time = one_line(time_node.get_text(" ", strip=True))
                if re.fullmatch(r"\d{1,2}:\d{2}", time):
                    records.append(rec("新月豪華", title=title, date=date_text, time=time, fmt=title, auditorium=auditorium, raw=f"{auditorium} {title} {time}"))
    if not source_hits and specials(page_text):
        source_hits.append(one_line(page_text, 500))
    return records, source_hits


def audit_halar() -> tuple[list[dict], list[str]]:
    raw = request_bytes(HALAR_URL, verify_ssl=False)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    records = []
    source_hits = []
    for film in soup.select(".film-item"):
        title_node = film.select_one(".film-title")
        title = one_line(title_node.get_text(" ", strip=True) if title_node else "")
        film_text = film.get_text(" ", strip=True)
        image_alts = [one_line(img.get("alt", "")) for img in film.select("img[alt]") if one_line(img.get("alt", ""))]
        source_blob = " | ".join([film_text, *image_alts])
        if specials(source_blob):
            source_hits.append(one_line(source_blob, 500))
        for session in film.select(".session"):
            date_node = session.select_one(".session-date")
            date_text = one_line(date_node.get_text(" ", strip=True) if date_node else "")
            for time_link in session.select("a.session-time"):
                time_node = time_link.select_one("time")
                time = one_line(time_node.get_text(strip=True) if time_node else "")
                attributes = [one_line(image.get("alt", "")) for image in time_link.select("img[alt]") if one_line(image.get("alt", ""))]
                auditorium = " / ".join(attributes)
                if re.fullmatch(r"\d{1,2}:\d{2}", time):
                    records.append(rec("哈拉", title=title, date=date_text, time=time, fmt=title, auditorium=auditorium, raw=f"{title} | {date_text} | {auditorium} | {time}"))
    return records, source_hits


def summarize(name: str, records: list[dict], source_hits: list[str]) -> dict:
    special_records = [r for r in records if r["source_specials"] or r["preserved_specials"]]
    unique = {}
    for r in special_records:
        key = (r["title"], r["date"], r["time"], r["format"], r["auditorium"])
        unique[key] = r
    special_records = list(unique.values())[:80]

    source_specials = sorted({token for hit in source_hits for token in specials(hit)})
    preserved = sorted({token for r in special_records for token in r["preserved_specials"]})
    frontend = sorted({token for r in special_records for token in r["frontend_tags"]})

    lost = sorted(set(source_specials) - set(preserved))
    preserved_but_unrecognized = sorted(set(preserved) - set(frontend))

    if not source_specials:
        verdict = "NO_LIVE_SPECIAL_FOUND"
    elif lost:
        verdict = "PARSER_GAP"
    elif preserved_but_unrecognized:
        verdict = "FRONTEND_RULE_GAP"
    else:
        verdict = "CURRENT_PIPELINE_OK"

    return {
        "cinema": name,
        "verdict": verdict,
        "source_specials": source_specials,
        "preserved_specials": preserved,
        "frontend_tags": frontend,
        "lost_by_parser": lost,
        "preserved_but_unrecognized": preserved_but_unrecognized,
        "source_hit_samples": list(dict.fromkeys(source_hits))[:20],
        "special_record_samples": special_records[:25],
        "record_count": len(records),
    }


def main() -> int:
    audits = [
        ("美麗華", audit_miramar),
        ("樂聲", audit_lux),
        ("威尼斯", audit_venice),
        ("金獅", audit_windlion),
        ("台鋁", audit_mld),
        ("新月豪華", audit_luna),
        ("哈拉", audit_halar),
    ]

    results = []
    for name, func in audits:
        try:
            records, source_hits = func()
            results.append(summarize(name, records, source_hits))
        except Exception as exc:
            results.append({
                "cinema": name,
                "verdict": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            })

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
