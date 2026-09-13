from __future__ import annotations

import argparse
import re
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from init_db import DEFAULT_DB_PATH, init_db


MIRANEW_CHAIN = {
    "chain_name": "美麗新影城",
    "chain_key": "miranew",
    "adapter_key": "miranew",
    "crawl_url": "https://www.miranewcinemas.com/Booking/Timetable",
    "notes": "Miranew Booking/Timetable scraper",
}

FIXED_CHAIN_LOCATIONS = [
    {
        "chain": {
            "chain_name": "天台影城",
            "chain_key": "skycine",
            "adapter_key": "skycine",
            "crawl_url": "https://www.skymovie.com.tw/",
            "notes": "SkyMovie New Taipei official website",
        },
        "locations": [
            {
                "location_name": "天台影城",
                "address": "新北市三重區重新路二段78號4樓",
                "city": "新北市",
                "source_location_code": "skycine-main",
                "location_url": "https://www.skymovie.com.tw/",
                "source_url": "https://www.skymovie.com.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "哈拉影城",
            "chain_key": "halar",
            "adapter_key": "halar",
            "crawl_url": "https://www.halarcinema.com.tw/",
            "notes": "Halar official website",
        },
        "locations": [
            {
                "location_name": "哈拉影城",
                "address": "台北市內湖區康寧路三段72號8樓",
                "city": "台北市",
                "source_location_code": "halar-main",
                "location_url": "https://www.halarcinema.com.tw/",
                "source_url": "https://www.halarcinema.com.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "美麗華影城",
            "chain_key": "miramar",
            "adapter_key": "miramar",
            "crawl_url": "https://www.miramarcinemas.tw/",
            "notes": "Miramar official website",
        },
        "locations": [
            {
                "location_name": "美麗華大直影城",
                "address": "台北市中山區敬業三路22號6樓",
                "city": "台北市",
                "source_location_code": "miramar-main",
                "location_url": "https://www.miramarcinemas.tw/",
                "source_url": "https://www.miramarcinemas.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "南台影城",
            "chain_key": "nantai",
            "adapter_key": "nantai",
            "crawl_url": "https://www.nt-movie.com.tw/",
            "notes": "Nan Tai official website",
        },
        "locations": [
            {
                "location_name": "南台影城",
                "address": "台南市中西區友愛街317號",
                "city": "台南市",
                "source_location_code": "nantai-main",
                "location_url": "https://www.nt-movie.com.tw/",
                "source_url": "https://www.nt-movie.com.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "樂聲影城",
            "chain_key": "luxcinema",
            "adapter_key": "luxcinema",
            "crawl_url": "https://www.luxcinema.com.tw/",
            "notes": "LUX Cinema official website",
        },
        "locations": [
            {
                "location_name": "樂聲影城",
                "address": "台北市萬華區武昌街二段85號",
                "city": "台北市",
                "source_location_code": "lux-main",
                "location_url": "https://www.luxcinema.com.tw/",
                "source_url": "https://www.luxcinema.com.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "台鋁影城",
            "chain_key": "mldc",
            "adapter_key": "mldc",
            "crawl_url": "https://www.mldcinema.com/",
            "notes": "MLD Cinema official website",
        },
        "locations": [
            {
                "location_name": "台鋁影城",
                "address": "高雄市前鎮區忠勤路8號",
                "city": "高雄市",
                "source_location_code": "mldc-main",
                "location_url": "https://www.mldcinema.com/",
                "source_url": "https://www.mldcinema.com/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "鴻金寶麻吉影城",
            "chain_key": "hkmovie",
            "adapter_key": "hkmovie",
            "crawl_url": "https://www.hkmovie.com.tw/",
            "notes": "Hong Jin Bao official website",
        },
        "locations": [
            {
                "location_name": "鴻金寶麻吉影城",
                "address": "新北市新莊區民安路188巷5號",
                "city": "新北市",
                "source_location_code": "hkmovie-main",
                "location_url": "https://www.hkmovie.com.tw/",
                "source_url": "https://www.hkmovie.com.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
    {
        "chain": {
            "chain_name": "光點華山電影館",
            "chain_key": "spot-huashan",
            "adapter_key": "spot-huashan",
            "crawl_url": "https://www.spot-hs.org.tw/",
            "notes": "SPOT Huashan official website",
        },
        "locations": [
            {
                "location_name": "光點華山電影館",
                "address": "台北市中正區八德路一段1號",
                "city": "台北市",
                "source_location_code": "spot-huashan-main",
                "location_url": "https://www.spot-hs.org.tw/",
                "source_url": "https://www.spot-hs.org.tw/",
                "notes": "Single-location official website",
            }
        ],
    },
]


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def extract_miranew_locations(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, dict[str, object]] = {}

    for node in soup.select("[data-cinema], [data-theater], option[value], a[href]"):
        text = " ".join(node.stripped_strings).strip()
        if "美麗新" not in text and "Miranew" not in text:
            continue

        code = (
            node.get("data-cinema")
            or node.get("data-theater")
            or node.get("value")
            or ""
        ).strip()
        href = (node.get("href") or "").strip()
        if not code and href:
            parsed = urlparse(href)
            match = re.search(r"(?:cinema|theater|site|sid)=([^&]+)", parsed.query, re.I)
            if match:
                code = match.group(1)
        if not code or code in {"0", "-1", "#"}:
            continue

        normalized_name = re.sub(r"\s+", " ", text)
        candidates[code] = {
            "location_name": normalized_name,
            "address": None,
            "city": None,
            "source_location_code": code,
            "location_url": urljoin(MIRANEW_CHAIN["crawl_url"], href) if href else MIRANEW_CHAIN["crawl_url"],
            "source_url": MIRANEW_CHAIN["crawl_url"],
            "notes": "Parsed from Miranew Booking/Timetable",
        }

    return list(candidates.values())


def apply_date_to_group(group: dict[str, object], show_date: str) -> dict[str, object]:
    # Existing fixed groups can contain a {date} placeholder in future additions.
    chain = dict(group["chain"])
    locations = []
    for raw_location in group["locations"]:
        location = dict(raw_location)
        for key in ("location_url", "source_url"):
            value = location.get(key)
            if isinstance(value, str):
                location[key] = value.replace("{date}", show_date)
        locations.append(location)
    return {"chain": chain, "locations": locations}


def upsert_chain(conn: sqlite3.Connection, chain: dict[str, object]) -> int:
    conn.execute(
        """
        INSERT INTO cinema_chains (chain_name, chain_key, adapter_key, crawl_url, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chain_key) DO UPDATE SET
            chain_name = excluded.chain_name,
            adapter_key = excluded.adapter_key,
            crawl_url = excluded.crawl_url,
            notes = excluded.notes,
            active = 1
        """,
        (
            chain["chain_name"],
            chain["chain_key"],
            chain["adapter_key"],
            chain["crawl_url"],
            chain.get("notes"),
        ),
    )
    row = conn.execute(
        "SELECT id FROM cinema_chains WHERE chain_key = ?",
        (chain["chain_key"],),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Unable to resolve chain id for {chain['chain_key']}")
    return int(row[0])


def upsert_location(conn: sqlite3.Connection, chain_id: int, location: dict[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO cinema_locations (
            chain_id,
            location_name,
            address,
            city,
            source_location_code,
            location_url,
            source_url,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chain_id, location_name) DO UPDATE SET
            address = COALESCE(excluded.address, cinema_locations.address),
            city = COALESCE(excluded.city, cinema_locations.city),
            source_location_code = excluded.source_location_code,
            location_url = excluded.location_url,
            source_url = excluded.source_url,
            notes = excluded.notes,
            active = 1
        """,
        (
            chain_id,
            location["location_name"],
            location.get("address"),
            location.get("city"),
            location.get("source_location_code"),
            location.get("location_url"),
            location.get("source_url"),
            location.get("notes"),
        ),
    )


def save_locations(miranew_locations: list[dict[str, object]], db_path: Path, show_date: str) -> int:
    init_db(db_path)
    saved = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        miranew_chain_id = upsert_chain(conn, MIRANEW_CHAIN)
        for location in miranew_locations:
            upsert_location(conn, miranew_chain_id, location)
            saved += 1

        for raw_group in FIXED_CHAIN_LOCATIONS:
            group = apply_date_to_group(raw_group, show_date)
            chain_id = upsert_chain(conn, group["chain"])
            for location in group["locations"]:
                upsert_location(conn, chain_id, location)
                saved += 1

    return saved


def load_miranew_locations(local_html: Path | None) -> tuple[list[dict[str, object]], str | None]:
    """Load Miranew dynamically without blocking refresh of fixed cinema locations."""
    try:
        if local_html:
            html = local_html.read_text(encoding="utf-8", errors="ignore")
        else:
            html = fetch_text(MIRANEW_CHAIN["crawl_url"])
        return extract_miranew_locations(html), None
    except Exception as exc:  # Source outage must not discard the independent fixed location set.
        return [], f"{type(exc).__name__}: {exc}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Miranew and smaller/single-location cinema locations into SQLite."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Show date for date-based cinema URLs.")
    parser.add_argument(
        "--miranew-html",
        type=Path,
        help="Optional local Miranew Booking/Timetable HTML path for offline parsing.",
    )
    args = parser.parse_args()

    miranew_locations, miranew_error = load_miranew_locations(args.miranew_html)
    if miranew_error:
        print(f"[MIRANEW] dynamic location refresh unavailable: {miranew_error}")
        print("[MIRANEW] continuing with versioned/fixed cinema locations")

    saved = save_locations(miranew_locations, args.db, args.date)

    print(f"Saved locations: {saved}")
    print("Miranew locations:")
    for location in miranew_locations:
        print(f"{location['source_location_code']} | {location['location_name']}")


if __name__ == "__main__":
    main()
