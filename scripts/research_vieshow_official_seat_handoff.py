#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

HOME = "https://www.vscinemas.com.tw/"


def compact_headers(headers):
    keep = {}
    for key in ("referer", "origin", "content-type"):
        if key in headers:
            keep[key] = headers[key]
    return keep


def main() -> int:
    out = {
        "dom": {},
        "script_hits": [],
        "api_sample": {},
        "click_trace": [],
        "errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()

        def on_request(request):
            url = request.url
            if any(
                token.lower() in url.lower()
                for token in (
                    "sessionseats",
                    "getlstdic",
                    "booking.aspx",
                    "voucher",
                    "ticketing",
                )
            ):
                out["click_trace"].append(
                    {
                        "event": "request",
                        "method": request.method,
                        "url": url,
                        "post_data": request.post_data,
                        "headers": compact_headers(request.headers),
                    }
                )

        def on_response(response):
            url = response.url
            if any(
                token.lower() in url.lower()
                for token in (
                    "sessionseats",
                    "getlstdic",
                    "booking.aspx",
                    "voucher",
                    "ticketing",
                )
            ):
                out["click_trace"].append(
                    {
                        "event": "response",
                        "status": response.status,
                        "url": url,
                    }
                )

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4000)

        out["dom"]["selects"] = page.locator("select").evaluate_all(
            """els => els.map(el => ({
                id: el.id,
                name: el.name,
                value: el.value,
                option_count: el.options.length,
                options: [...el.options].slice(0, 8).map(o => ({text:o.textContent.trim(), value:o.value}))
            }))"""
        )
        out["dom"]["seat_controls"] = page.locator("a,button,input").evaluate_all(
            """els => els.map(el => ({
                tag: el.tagName,
                id: el.id,
                name: el.getAttribute('name'),
                type: el.getAttribute('type'),
                text: (el.textContent || el.value || '').trim(),
                href: el.getAttribute('href'),
                onclick: el.getAttribute('onclick'),
                form_action: el.form ? el.form.getAttribute('action') : null,
                form_method: el.form ? el.form.getAttribute('method') : null,
            })).filter(x => /座位|訂票|快速/.test(x.text) || /SessionSeats/i.test(x.href || '') || /SessionSeats/i.test(x.onclick || ''))"""
        )
        out["dom"]["forms"] = page.locator("form").evaluate_all(
            """els => els.map(el => ({
                id: el.id,
                name: el.getAttribute('name'),
                action: el.getAttribute('action'),
                method: el.getAttribute('method')
            }))"""
        )

        # Inspect same-origin script bodies for the actual quick-booking implementation.
        script_urls = page.locator("script[src]").evaluate_all(
            """els => els.map(el => el.src).filter(Boolean)"""
        )
        for url in script_urls:
            try:
                resp = context.request.get(url, timeout=30_000)
                if not resp.ok:
                    continue
                text = resp.text()
            except Exception:
                continue
            lowered = text.lower()
            if not any(
                token in lowered
                for token in (
                    "sessionseats",
                    "getlstdicsession",
                    "getlstdicmovie",
                    "查看座位",
                )
            ):
                continue
            for needle in (
                "SessionSeats",
                "GetLstDicSession",
                "GetLstDicMovie",
                "查看座位",
            ):
                for match in re.finditer(re.escape(needle), text, re.I):
                    start = max(0, match.start() - 900)
                    end = min(len(text), match.end() + 1500)
                    out["script_hits"].append(
                        {
                            "script": url,
                            "needle": needle,
                            "snippet": text[start:end],
                        }
                    )
                    if len(out["script_hits"]) >= 20:
                        break
                if len(out["script_hits"]) >= 20:
                    break
            if len(out["script_hits"]) >= 20:
                break

        # Use the public quick-booking API to discover one live session.
        def api_json(path: str):
            return page.evaluate(
                """async path => {
                    const r = await fetch(path, {headers:{Accept:'application/json,text/plain,*/*'}});
                    return {status:r.status, data: await r.json()};
                }""",
                path,
            )

        cinemas = api_json("/api/GetLstDicCinema")
        out["api_sample"]["cinemas_status"] = cinemas["status"]
        chosen = None
        for cinema in cinemas["data"]:
            cval = str(cinema.get("strValue") or cinema.get("value") or "")
            ctext = str(cinema.get("strText") or cinema.get("text") or "")
            if not cval:
                continue
            movies_path = "/api/GetLstDicMovie?" + urllib.parse.urlencode({"cinema": cval}, safe="|")
            movies = api_json(movies_path)
            if movies["status"] != 200 or not movies["data"]:
                continue
            movie = next(
                (
                    m
                    for m in movies["data"]
                    if str(m.get("strValue") or m.get("value") or "").strip()
                ),
                None,
            )
            if not movie:
                continue
            mval = str(movie.get("strValue") or movie.get("value") or "")
            mtext = str(movie.get("strText") or movie.get("text") or "")
            dates_path = "/api/GetLstDicDate?" + urllib.parse.urlencode(
                {"cinema": cval, "movie": mval}, safe="|/"
            )
            dates = api_json(dates_path)
            if dates["status"] != 200 or not dates["data"]:
                continue
            date_item = next(
                (
                    d
                    for d in dates["data"]
                    if str(d.get("strValue") or d.get("value") or d.get("strText") or d.get("text") or "").strip()
                ),
                None,
            )
            if not date_item:
                continue
            dval = str(
                date_item.get("strValue")
                or date_item.get("value")
                or date_item.get("strText")
                or date_item.get("text")
                or ""
            )
            sessions_path = "/api/GetLstDicSession?" + urllib.parse.urlencode(
                {"cinema": cval, "movie": mval, "date": dval}, safe="|/"
            )
            sessions = api_json(sessions_path)
            if sessions["status"] != 200 or not sessions["data"]:
                continue
            session = next(
                (
                    s
                    for s in sessions["data"]
                    if str(s.get("strValue") or s.get("value") or "").strip()
                ),
                None,
            )
            if not session:
                continue
            chosen = {
                "cinema_text": ctext,
                "cinema_value": cval,
                "movie_text": mtext,
                "movie_value": mval,
                "date_value": dval,
                "session_text": str(session.get("strText") or session.get("text") or ""),
                "session_value": str(session.get("strValue") or session.get("value") or ""),
            }
            break

        out["api_sample"]["chosen"] = chosen

        # If the homepage has the known quick-booking selects, drive them exactly as a user would.
        if chosen:
            selectors = {
                "cinema": "#CinemaNameTWInfoS",
                "movie": "#MovieNameTWInfoS",
                "date": "#DateNameTWInfoS",
                "session": "#SessionNameTWInfoS",
            }
            try:
                if page.locator(selectors["cinema"]).count():
                    page.select_option(selectors["cinema"], value=chosen["cinema_value"])
                    page.locator(selectors["cinema"]).dispatch_event("change")
                    page.wait_for_timeout(1000)

                    movie_select = page.locator(selectors["movie"])
                    if movie_select.count():
                        values = movie_select.locator("option").evaluate_all(
                            "opts => opts.map(o => ({text:o.textContent.trim(), value:o.value}))"
                        )
                        target = next(
                            (x for x in values if x["value"] == chosen["movie_value"]),
                            None,
                        )
                        if target:
                            page.select_option(selectors["movie"], value=target["value"])
                            page.locator(selectors["movie"]).dispatch_event("change")
                            page.wait_for_timeout(1000)

                    date_select = page.locator(selectors["date"])
                    if date_select.count():
                        values = date_select.locator("option").evaluate_all(
                            "opts => opts.map(o => ({text:o.textContent.trim(), value:o.value}))"
                        )
                        target = next(
                            (x for x in values if x["value"] == chosen["date_value"] or x["text"] == chosen["date_value"]),
                            None,
                        )
                        if target:
                            page.select_option(selectors["date"], value=target["value"])
                            page.locator(selectors["date"]).dispatch_event("change")
                            page.wait_for_timeout(1000)

                    session_select = page.locator(selectors["session"])
                    if session_select.count():
                        values = session_select.locator("option").evaluate_all(
                            "opts => opts.map(o => ({text:o.textContent.trim(), value:o.value}))"
                        )
                        target = next(
                            (x for x in values if x["value"] == chosen["session_value"]),
                            None,
                        )
                        if target:
                            page.select_option(selectors["session"], value=target["value"])
                            page.locator(selectors["session"]).dispatch_event("change")
                            page.wait_for_timeout(500)

                out["dom"]["after_selection"] = {
                    "url": page.url,
                    "selects": page.locator("select").evaluate_all(
                        """els => els.map(el => ({id:el.id, value:el.value}))"""
                    ),
                    "seat_controls": page.locator("a,button,input").evaluate_all(
                        """els => els.map(el => ({
                            tag:el.tagName,
                            id:el.id,
                            text:(el.textContent || el.value || '').trim(),
                            href:el.getAttribute('href'),
                            onclick:el.getAttribute('onclick')
                        })).filter(x => /座位/.test(x.text) || /SessionSeats/i.test(x.href || '') || /SessionSeats/i.test(x.onclick || ''))"""
                    ),
                }

                # Click a visible "查看座位" control naturally and inspect resulting navigation.
                seat_candidates = page.locator("a,button,input").filter(has_text="查看座位")
                if not seat_candidates.count():
                    seat_candidates = page.locator("input[value*='查看座位']")
                if seat_candidates.count():
                    popup_pages = []
                    context.on("page", lambda pg: popup_pages.append(pg))
                    before = page.url
                    seat_candidates.first.click(timeout=10_000)
                    page.wait_for_timeout(2500)
                    result_page = popup_pages[-1] if popup_pages else page
                    try:
                        result_page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    except Exception:
                        pass
                    out["dom"]["after_seat_click"] = {
                        "before_url": before,
                        "current_page_url": page.url,
                        "popup_count": len(popup_pages),
                        "result_url": result_page.url,
                        "result_title": result_page.title(),
                        "result_referrer": result_page.evaluate("document.referrer"),
                    }
                else:
                    out["errors"].append("No visible 查看座位 control found after selection")
            except Exception as exc:
                out["errors"].append(f"drive_quick_booking: {type(exc).__name__}: {exc}")

        context.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
