from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_movie_showtimes as showtimes


def dump(label, value):
    print("\n=== " + label + " ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str)[:30000])


def first_nonempty(sequence):
    for item in sequence or []:
        if item:
            return item
    return None


def probe_broadway():
    for code in ("Taipei", "Zhubei"):
        try:
            text = showtimes.request_text(
                showtimes.BROADWAY_API.format(code=code),
                headers={
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": f"https://www.broadway-cineplex.com.tw/book.html?obj={code}&v25080101",
                },
                verify_ssl=False,
            )
            payload = json.loads(text)
            movie = next(
                (m for m in payload.get("Data", []) if any(g.get("subtimedata") for g in m.get("timedata", []))),
                None,
            )
            group = first_nonempty(movie.get("timedata", [])) if movie else None
            item = first_nonempty(group.get("subtimedata", [])) if group else None
            dump(f"BROADWAY {code} movie keys", sorted(movie.keys()) if movie else [])
            dump(f"BROADWAY {code} group", group)
            dump(f"BROADWAY {code} session", item)
        except Exception as exc:
            dump(f"BROADWAY {code} ERROR", {"type": type(exc).__name__, "error": str(exc)})


def probe_miranew():
    try:
        text = showtimes.request_text(
            showtimes.MIRANEW_TIMETABLE_URL,
            headers={"Referer": "https://www.miranewcinemas.com/"},
        )
        payload = showtimes.extract_miranew_payload(text)
        cinema = first_nonempty(payload.get("Data", {}).get("CinemaGroup", []))
        movie = first_nonempty(cinema.get("MovieInfo", [])) if cinema else None
        day = first_nonempty(movie.get("ShowDateList", [])) if movie else None
        hall = first_nonempty(day.get("ShowTimeList", [])) if day else None
        session = first_nonempty(hall.get("SessionList", [])) if hall else None
        dump("MIRANEW cinema", cinema and {k: v for k, v in cinema.items() if k != "MovieInfo"})
        dump("MIRANEW movie keys", sorted(movie.keys()) if movie else [])
        dump("MIRANEW movie identity", movie and {k: movie.get(k) for k in movie if "id" in k.lower() or "name" in k.lower()})
        dump("MIRANEW hall", hall and {k: v for k, v in hall.items() if k != "SessionList"})
        dump("MIRANEW session", session)
    except Exception as exc:
        dump("MIRANEW ERROR", {"type": type(exc).__name__, "error": str(exc)})


def probe_skcinemas():
    try:
        entry = showtimes.SKCINEMAS_FILMS_URL + "?c=1001"
        headers = showtimes.capture_skcinemas_headers(entry, headless=False, wait_ms=6000)
        payload = showtimes.request_json(
            showtimes.SKCINEMAS_SESSION_API,
            method="POST",
            payload={"CustomerID": "", "Mobile": "", "CinemasID": "1001"},
            headers=headers,
        )
        data = payload.get("data") or {}
        film = first_nonempty(data.get("SessionFilm", []))
        session = first_nonempty(data.get("Session", []))
        dump("SKCINEMAS SessionFilm", film)
        dump("SKCINEMAS Session", session)
    except Exception as exc:
        dump("SKCINEMAS ERROR", {"type": type(exc).__name__, "error": str(exc)})


def inspect_booking_page(page, label, url, row_selector, time_selector, action_text):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        rows = page.locator(row_selector)
        if rows.count() == 0:
            dump(label + " DOM ERROR", {"url": page.url, "reason": "row selector missing", "title": page.title()})
            return
        row = rows.first
        times = row.locator(time_selector)
        dump(label + " first row", {
            "url": page.url,
            "text": row.inner_text()[:5000],
            "time_count": times.count(),
            "time_outer": times.first.evaluate("(el) => el.outerHTML") if times.count() else "",
        })
        if times.count():
            times.first.click()
            page.wait_for_timeout(800)
        action = row.get_by_text(action_text, exact=False)
        if action.count():
            node = action.first
            dump(label + " action after time select", {
                "outer": node.evaluate("(el) => el.outerHTML"),
                "href": node.get_attribute("href"),
                "onclick": node.get_attribute("onclick"),
            })
            before = page.url
            requests = []
            def on_request(req):
                if req.is_navigation_request() or any(x in req.url.lower() for x in ("book", "ticket", "login", "order")):
                    requests.append({"method": req.method, "url": req.url, "post_data": req.post_data})
            page.on("request", on_request)
            try:
                node.click(timeout=5000)
                page.wait_for_timeout(2500)
            except Exception as click_exc:
                requests.append({"click_error": str(click_exc)})
            dump(label + " after action", {"before": before, "after": page.url, "requests": requests[-20:]})
        else:
            dump(label + " action missing", {"text": action_text})
    except Exception as exc:
        dump(label + " ERROR", {"type": type(exc).__name__, "error": str(exc), "url": getattr(page, "url", "")})


def probe_browser_flows():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(locale="zh-TW", timezone_id="Asia/Taipei", viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        inspect_booking_page(
            page,
            "CENTURY NANGANG",
            "https://www.centuryasia.com.tw/book.html?sid=Nangang&ver=0fKKApRlrx8=",
            ".content-row",
            ".time:not(.disable)",
            "立即前往訂票",
        )
        page = ctx.new_page()
        inspect_booking_page(
            page,
            "BROADWAY TAIPEI",
            "https://www.broadway-cineplex.com.tw/book.html?obj=Taipei&v25080101",
            ".content-row, .movie-row, .movie-item",
            ".time, [class*=time]",
            "BUY TICKET",
        )
        ctx.close()
        browser.close()


def main():
    probe_broadway()
    probe_miranew()
    probe_skcinemas()
    probe_browser_flows()


if __name__ == "__main__":
    main()
