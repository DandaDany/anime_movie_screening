#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse

from bs4 import BeautifulSoup

from fetch_movie_showtimes import (
    HALAR_URL,
    LUNA_URL,
    LUX_URL,
    MIRAMAR_URL,
    MLD_URL,
    VENICE_URL,
    WINDLION_URL,
    render_page_html,
    request_bytes,
    text_blocks_from_html,
)

SPECIAL_RE = re.compile(
    r"(?i)(imax|4dx|4d\+|mx-?4d|screen\s*-?x|titan|ultra|luxe|"
    r"dolby|atmos|infinity\s*vision|\bxl\b|\bvip\b|free\s*laxx|"
    r"kids\+?|v廳|巨幕|水影|hfr\s*3d|3d)"
)


def uniq(values):
    out = []
    seen = set()
    for value in values:
        value = re.sub(r"\s+", " ", str(value or "")).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def hits(text):
    return uniq(m.group(0) for m in SPECIAL_RE.finditer(text or ""))


def audit_miramar():
    raw = request_bytes(MIRAMAR_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    rows = []
    for movie in soup.select(".timetable_list"):
        title_node = movie.select_one(".movie_info .title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        for block in movie.select(".time_list_right > .block"):
            room_node = block.select_one(".room")
            room = room_node.get_text(" ", strip=True).replace("watch_later", "").strip() if room_node else ""
            token_hits = hits(" ".join([title, room, block.get_text(" ", strip=True)]))
            if token_hits:
                rows.append({
                    "title": title,
                    "source_special": token_hits,
                    "current_format": room or None,
                    "current_auditorium": None,
                    "preserved_text": room,
                })
    return {"source":"美麗華影城","rows":rows}


def audit_lux():
    raw = request_bytes(LUX_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    rows = []
    for movie in soup.select(".movie_list_box"):
        title_node = movie.select_one("h1")
        title = title_node.get_text(" ", strip=True).replace("立即訂票", "").strip() if title_node else ""
        for item in movie.select("ul li"):
            text = item.get_text(" ", strip=True)
            match = re.search(r"(\d{1,2}:\d{2})(?:\s*\|\s*([A-Za-z0-9]+))?", text)
            auditorium = match.group(2) if match else None
            token_hits = hits(" ".join([title, text]))
            if token_hits:
                rows.append({
                    "title": title,
                    "source_special": token_hits,
                    "current_format": title or None,
                    "current_auditorium": auditorium,
                    "preserved_text": " / ".join(v for v in [title, auditorium] if v),
                })
    return {"source":"樂聲影城","rows":rows}


def audit_venice():
    rows = []
    for page_number in range(1, 5):
        url = VENICE_URL.format(page=page_number)
        try:
            html = render_page_html(url, wait_ms=4000)
        except Exception as exc:
            rows.append({"page":page_number,"error":f"{type(exc).__name__}: {exc}"})
            continue
        soup = BeautifulSoup(html, "html.parser")
        lines = [x.strip() for x in soup.get_text("\n", strip=True).splitlines() if x.strip()]
        for i, line in enumerate(lines):
            token_hits = hits(line)
            if not token_hits:
                continue
            nearby = " | ".join(lines[max(0,i-3):min(len(lines),i+4)])
            rows.append({
                "page":page_number,
                "source_line":line,
                "source_special":token_hits,
                "nearby":nearby[:500],
                "note":"generic parser only preserves matched movie title as format; auditorium regex is limited",
            })
    return {"source":"威尼斯影城","rows":rows}


def audit_windlion():
    html = render_page_html(f"{WINDLION_URL}#anchor", wait_ms=6000)
    lines = text_blocks_from_html(html)
    rows = []
    current_title = None
    current_language = None
    for line in lines:
        if not re.search(r"\d{1,2}:\d{2}", line) and not line.startswith("語言") and not re.match(r"\d{4}-\d{2}-\d{2}", line):
            # This approximates the crawler's current_title updates when a movie title is encountered.
            if hits(line):
                current_title = line
        if line.startswith("語言"):
            current_language = line.replace("語言", "").replace(":", "").strip()
        match = re.search(r"(\d{1,2}:\d{2})\(([^)]+)\)", line)
        if match:
            auditorium = match.group(2)
            token_hits = hits(" ".join([current_title or "", current_language or "", auditorium, line]))
            if token_hits:
                fmt = " ".join(v for v in [current_title, current_language] if v)
                rows.append({
                    "source_line":line,
                    "source_special":token_hits,
                    "current_format_approx":fmt or None,
                    "current_auditorium":auditorium,
                    "preserved_text":" / ".join(v for v in [fmt, auditorium] if v),
                })
        elif hits(line):
            rows.append({
                "source_line":line,
                "source_special":hits(line),
                "note":"special token appears on page outside a parsed time(auditorium) line",
            })
    return {"source":"金獅影城","rows":rows}


def audit_mld():
    raw = request_bytes(MLD_URL)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    rows = []
    for movie in soup.select("dl"):
        title_node = movie.select_one("dt")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        token_hits = hits(movie.get_text(" ", strip=True))
        if token_hits:
            rows.append({
                "title":title,
                "source_special":token_hits,
                "current_format":title or None,
                "current_auditorium":None,
                "preserved_text":title,
            })
    # fallback because site markup may not be dl-based anymore
    if not rows:
        for line in text_blocks_from_html(raw):
            if hits(line):
                rows.append({"source_line":line,"source_special":hits(line),"note":"special token present in source text"})
    return {"source":"台鋁影城","rows":rows}


def audit_luna():
    raw = request_bytes(LUNA_URL, headers={"Referer":"https://www.lunacinemax.com.tw/"})
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    rows = []
    for title_node in soup.select("span[id$='NAME_CHTLabel']"):
        title = title_node.get_text(" ", strip=True)
        movie_table = title_node.find_parent("table")
        movie_row = movie_table.find_parent("tr") if movie_table else None
        screen_table = movie_row.find_parent("table") if movie_row else None
        screen_row = screen_table.find_parent("tr") if screen_table else None
        hall_node = screen_row.select_one("span[id$='SCREEN_NAMELabel']") if screen_row else None
        auditorium = hall_node.get_text(" ", strip=True) if hall_node else ""
        token_hits = hits(" ".join([title, auditorium]))
        if token_hits:
            rows.append({
                "title":title,
                "source_special":token_hits,
                "current_format":title or None,
                "current_auditorium":auditorium or None,
                "preserved_text":" / ".join(v for v in [title,auditorium] if v),
            })
    if not rows:
        for line in text_blocks_from_html(raw):
            if hits(line):
                rows.append({"source_line":line,"source_special":hits(line),"note":"special token present in source text"})
    return {"source":"新月豪華影城","rows":rows}


def audit_halar():
    raw = request_bytes(HALAR_URL, verify_ssl=False)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    rows = []
    for film in soup.select(".film-item"):
        title_node = film.select_one(".film-title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        for time_link in film.select("a.session-time"):
            attrs = uniq(img.get("alt","").strip() for img in time_link.select("img[alt]"))
            source_text = " ".join([title, *attrs, time_link.get_text(" ", strip=True)])
            token_hits = hits(source_text)
            if token_hits:
                auditorium = " / ".join(attrs) or None
                rows.append({
                    "title":title,
                    "source_special":token_hits,
                    "current_format":title or None,
                    "current_auditorium":auditorium,
                    "preserved_text":" / ".join(v for v in [title,auditorium] if v),
                })
    if not rows:
        for line in text_blocks_from_html(raw):
            if hits(line):
                rows.append({"source_line":line,"source_special":hits(line),"note":"special token present in source text"})
    return {"source":"哈拉影城","rows":rows}


def summarize(item):
    tokens = uniq(
        token
        for row in item.get("rows",[])
        for token in row.get("source_special",[])
    )
    preserved = []
    missing = []
    for row in item.get("rows",[]):
        text = row.get("preserved_text","")
        for token in row.get("source_special",[]):
            if token.lower() in text.lower():
                preserved.append(token)
            else:
                missing.append(token)
    return {
        "source":item["source"],
        "source_tokens":uniq(tokens),
        "preserved_by_current_parser":uniq(preserved),
        "not_preserved_by_current_parser":uniq(missing),
        "sample_rows":item.get("rows",[])[:12],
    }



# Diagnostic: inspect special-hall markup that the current parsers may not preserve.
def inspect_halar_markup():
    raw = request_bytes(HALAR_URL, verify_ssl=False)
    soup = BeautifulSoup(raw, "html.parser", from_encoding="utf-8")
    out = []
    seen = set()
    for link in soup.select("a.session-time"):
        for img in link.select("img"):
            item = {
                "src": img.get("src"),
                "alt": img.get("alt"),
                "class": img.get("class"),
                "title": img.get("title"),
                "parent_class": link.get("class"),
                "text": link.get_text(" ", strip=True),
            }
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(item)
    return out[:80]


def inspect_windlion_markup():
    html = render_page_html(f"{WINDLION_URL}#anchor", wait_ms=6000)
    lines = text_blocks_from_html(html)
    return [line for line in lines if re.search(r"\d{1,2}:\d{2}\([^)]*\)", line)][:120]


def inspect_venice_dom():
    out = []
    html = render_page_html(VENICE_URL.format(page=1), wait_ms=4000)
    soup = BeautifulSoup(html, "html.parser")
    for heading in soup.select("h1, h2, h3, h4"):
        title = heading.get_text(" ", strip=True)
        if "蜘蛛人：重生日" not in title:
            continue
        ancestry = []
        cursor = heading
        for _ in range(5):
            cursor = cursor.parent
            if cursor is None:
                break
            ancestry.append({
                "tag": cursor.name,
                "class": cursor.get("class"),
                "id": cursor.get("id"),
                "heading_count": len(cursor.select("h1, h2, h3, h4")),
                "time_count": len(re.findall(r"\\b\\d{1,2}:\\d{2}\\b", cursor.get_text(" ", strip=True))),
                "text": cursor.get_text(" ", strip=True)[:1000],
                "html": str(cursor)[:2400],
            })
        out.append({"title": title, "ancestry": ancestry})
    return out[:12]

def main():
    audits=[]
    for fn in [audit_miramar,audit_lux,audit_venice,audit_windlion,audit_mld,audit_luna,audit_halar]:
        try:
            audits.append(summarize(fn()))
        except Exception as exc:
            audits.append({"source":fn.__name__,"error":f"{type(exc).__name__}: {exc}"})
    print(json.dumps({
        "audits": audits,
        "halar_markup": inspect_halar_markup(),
        "windlion_time_lines": inspect_windlion_markup(),
        "venice_dom": inspect_venice_dom(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# One-off DOM diagnostic for production parser design.
def _debug_venice_h2_cards():
    html = render_page_html(VENICE_URL.format(page=1), wait_ms=4000)
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for h in soup.find_all(["h1","h2","h3","h4"]):
        text = h.get_text(" ", strip=True)
        if "蜘蛛人：重生日" not in text:
            continue
        cursor = h
        ancestry = []
        for _ in range(5):
            cursor = cursor.parent
            if cursor is None:
                break
            ancestry.append({
                "tag": cursor.name,
                "class": cursor.get("class"),
                "id": cursor.get("id"),
                "h2_count": len(cursor.find_all("h2")),
                "time_count": len(re.findall(r"\\b\\d{1,2}:\\d{2}\\b", cursor.get_text(" ", strip=True))),
                "text": cursor.get_text(" ", strip=True)[:1200],
                "html": str(cursor)[:2200],
            })
        out.append({"heading": text, "ancestry": ancestry})
    print(json.dumps({"venice_h2_cards": out[:12]}, ensure_ascii=False, indent=2))

if __name__ == "__debug__":
    _debug_venice_h2_cards()
