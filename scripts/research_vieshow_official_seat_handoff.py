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

        # Drive the official quick-booking UI using the real name attributes.
        if chosen:
            try:
                def wait_option(selector: str, value: str):
                    page.wait_for_function(
                        """([selector, value]) => {
                            const el = document.querySelector(selector);
                            return !!el && [...el.options].some(o => o.value === value);
                        }""",
                        arg=[selector, value],
                        timeout=10_000,
                    )

                wait_option("[name=cinema]", chosen["cinema_value"])
                page.select_option("[name=cinema]", value=chosen["cinema_value"])
                page.locator("[name=cinema]").dispatch_event("change")

                wait_option("[name=movie]", chosen["movie_value"])
                page.select_option("[name=movie]", value=chosen["movie_value"])
                page.locator("[name=movie]").dispatch_event("change")

                wait_option("[name=date]", chosen["date_value"])
                page.select_option("[name=date]", value=chosen["date_value"])
                page.locator("[name=date]").dispatch_event("change")

                wait_option("[name=session]", chosen["session_value"])
                page.select_option("[name=session]", value=chosen["session_value"])
                page.locator("[name=session]").dispatch_event("change")
                page.wait_for_timeout(500)

                out["dom"]["after_selection"] = {
                    "url": page.url,
                    "quick_booking_values": {
                        name: page.locator(f"[name={name}]").input_value()
                        for name in ("cinema", "movie", "date", "session")
                    },
                    "seat_href": page.locator("#SessionSeats").get_attribute("href"),
                    "seat_target": page.locator("#SessionSeats").get_attribute("target"),
                    "seat_outer_html": page.locator("#SessionSeats").evaluate("el => el.outerHTML"),
                }

                popup_pages = []
                context.on("page", lambda pg: popup_pages.append(pg))
                seat_link = page.locator("#SessionSeats")
                before = page.url
                seat_link.click(timeout=10_000)
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
                    "seat_grid_count": result_page.locator("#GridViewSessionSeats").count(),
                }

                # Test whether VIESHOW supports external URL prefill for the four quick-booking values.
                prefill_query = urllib.parse.urlencode(
                    {
                        "cinema": chosen["cinema_value"],
                        "movie": chosen["movie_value"],
                        "date": chosen["date_value"],
                        "session": chosen["session_value"],
                    },
                    safe="|/",
                )
                prefill = context.new_page()
                prefill.goto(HOME + "?" + prefill_query, wait_until="domcontentloaded", timeout=60_000)
                prefill.wait_for_timeout(2500)
                out["dom"]["homepage_query_prefill"] = {
                    "url": prefill.url,
                    "values": {
                        name: prefill.locator(f"[name={name}]").input_value()
                        for name in ("cinema", "movie", "date", "session")
                        if prefill.locator(f"[name={name}]").count()
                    },
                    "seat_href": prefill.locator("#SessionSeats").get_attribute("href")
                    if prefill.locator("#SessionSeats").count()
                    else None,
                }

                # Inspect the separate official search_seat GET form. This is not the
                # quick-booking form, but verify whether it can serve as a supported
                # prefill handoff.
                out["dom"]["search_seat_form_controls"] = page.locator(
                    "form[action*='search_seat.aspx'] input, form[action*='search_seat.aspx'] select"
                ).evaluate_all(
                    """els => els.map(el => ({
                        tag: el.tagName,
                        name: el.getAttribute('name'),
                        type: el.getAttribute('type'),
                        value: el.value,
                        options: el.tagName === 'SELECT'
                          ? [...el.options].slice(0,5).map(o => ({text:o.textContent.trim(), value:o.value}))
                          : null
                    }))"""
                )

                search_page = context.new_page()
                search_url = (
                    "https://www.vscinemas.com.tw/vsTicketing/ticketing/search_seat.aspx?"
                    + prefill_query
                )
                resp = search_page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
                search_page.wait_for_timeout(1500)
                out["dom"]["search_seat_prefill_test"] = {
                    "requested_url": search_url,
                    "status": resp.status if resp else None,
                    "final_url": search_page.url,
                    "title": search_page.title(),
                    "quick_booking_values": {
                        name: search_page.locator(f"[name={name}]").input_value()
                        for name in ("cinema", "movie", "date", "session")
                        if search_page.locator(f"[name={name}]").count()
                    },
                }
            except Exception as exc:
                out["errors"].append(f"drive_quick_booking: {type(exc).__name__}: {exc}")

        context.close()
        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
