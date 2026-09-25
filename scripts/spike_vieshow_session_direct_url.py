#!/usr/bin/env python3
"""End-to-end VIESHOW quick-booking session-ID and direct-seat spike.

Walks the official quick-booking selects only. It does not reserve or purchase seats.
"""

from __future__ import annotations
import json
import re
from playwright.sync_api import sync_playwright

HOME = "https://www.vscinemas.com.tw/"
SEAT_URL = "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
VOUCHER_DEFAULT = "https://sales.vscinemas.com.tw/VoucherTicketing/Default.aspx"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TARGET_CINEMAS = [
    "台北信義威秀影城",
    "MUVIE CINEMAS 台北松仁",
    "高雄大遠百威秀影城",
]


def emit(event, **data):
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def context(browser):
    return browser.new_context(
        locale="zh-TW", timezone_id="Asia/Taipei", user_agent=UA,
        viewport={"width": 1366, "height": 900}
    )


def options(page, name):
    return page.locator(f'select[name="{name}"]').evaluate(
        """s => Array.from(s.options).map(o => ({
            value: (o.value || '').trim(),
            text: (o.textContent || '').trim(),
            disabled: !!o.disabled
        }))"""
    )


def choose_first_nonempty(page, name):
    opts = options(page, name)
    candidates = [o for o in opts if o["value"] and not o["disabled"]]
    emit("options", select=name, count=len(opts), options=opts[:30])
    if not candidates:
        return None
    chosen = candidates[0]
    page.locator(f'select[name="{name}"]').select_option(chosen["value"], timeout=10000)
    page.wait_for_timeout(3000)
    emit("chosen", select=name, chosen=chosen)
    return chosen


def find_cinema_value(page, cinema_text):
    opts = options(page, "cinema")
    for o in opts:
        if cinema_text == o["text"]:
            return o
    for o in opts:
        if cinema_text in o["text"]:
            return o
    return None


def trace_one(browser, cinema_text):
    ctx = context(browser)
    page = ctx.new_page()
    requests = []
    page.on(
        "request",
        lambda req: requests.append({
            "method": req.method,
            "url": req.url,
            "type": req.resource_type,
            "post_data": req.post_data,
        }) if req.resource_type in ("xhr", "fetch") else None,
    )
    page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(6500)

    cinema = find_cinema_value(page, cinema_text)
    if not cinema:
        emit("cinema_missing", cinema_text=cinema_text, all_cinemas=options(page, "cinema"))
        ctx.close()
        return None

    page.locator('select[name="cinema"]').select_option(cinema["value"], timeout=10000)
    page.wait_for_timeout(3500)
    emit("cinema_chosen", cinema=cinema)

    movie = choose_first_nonempty(page, "movie")
    if not movie:
        emit("no_movie", cinema=cinema)
        ctx.close()
        return None

    date = choose_first_nonempty(page, "date")
    if not date:
        emit("no_date", cinema=cinema, movie=movie)
        ctx.close()
        return None

    session_opts = options(page, "session")
    emit(
        "session_options",
        cinema=cinema,
        movie=movie,
        date=date,
        count=len(session_opts),
        options=session_opts[:50],
    )
    sessions = [o for o in session_opts if o["value"] and not o["disabled"]]
    if not sessions:
        emit("no_session", cinema=cinema, movie=movie, date=date)
        ctx.close()
        return None

    session = sessions[0]
    page.locator('select[name="session"]').select_option(session["value"], timeout=10000)
    page.wait_for_timeout(1500)

    form = page.locator('select[name="session"]').evaluate(
        """s => {
            const f = s.closest('form');
            return f ? {
                action: f.action || '',
                method: f.method || '',
                html: f.outerHTML.slice(0, 5000)
            } : null;
        }"""
    )
    emit("session_chosen", cinema=cinema, movie=movie, date=date, session=session, form=form)
    emit("quick_booking_requests", cinema=cinema, requests=requests[-60:])

    result = {
        "cinema": cinema,
        "movie": movie,
        "date": date,
        "session": session,
        "form": form,
    }
    ctx.close()
    return result


def parse_session_value(value):
    nums = re.findall(r"\d+", value or "")
    return nums


def direct_check(browser, cinema_code, session_id, label):
    out = []
    for warm in (False, True):
        ctx = context(browser)
        page = ctx.new_page()
        mode = "warm" if warm else "fresh"
        url = f"{SEAT_URL}?cinemacode={cinema_code}&txtSessionId={session_id}"
        try:
            if warm:
                page.goto(VOUCHER_DEFAULT, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(1200)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2500)
            body = page.locator("body").inner_text(timeout=5000)
            record = {
                "label": label,
                "mode": mode,
                "cinemacode": cinema_code,
                "session_id": session_id,
                "status": resp.status if resp else None,
                "requested": url,
                "final_url": page.url,
                "title": page.title(),
                "same_seat_path": "/voucherticketing/sessionseats.aspx" in page.url.lower(),
                "body_excerpt": re.sub(r"\s+", " ", body).strip()[:700],
            }
        except Exception as exc:
            record = {
                "label": label, "mode": mode, "cinemacode": cinema_code,
                "session_id": session_id, "requested": url, "final_url": page.url,
                "status": None, "same_seat_path": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        emit("direct_check", **record)
        out.append(record)
        ctx.close()
    return out


def main():
    traces = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        for cinema_text in TARGET_CINEMAS:
            trace = trace_one(browser, cinema_text)
            if trace:
                traces.append(trace)

        # The cinema select value is documented by the live page as "<numeric>|<shortcode>".
        # Session value is inspected before deciding how to parse it.
        tests = []
        for trace in traces:
            cinema_value = trace["cinema"]["value"]
            cinema_code = cinema_value.split("|", 1)[0]
            session_value = trace["session"]["value"]
            nums = parse_session_value(session_value)
            emit(
                "candidate_parse",
                cinema=trace["cinema"],
                session=trace["session"],
                numeric_cinemacode=cinema_code,
                session_numeric_parts=nums,
            )
            if nums:
                # Prefer the last numeric component: values may be composite.
                tests.extend(direct_check(
                    browser, cinema_code, nums[-1],
                    trace["cinema"]["text"],
                ))

        browser.close()

    emit(
        "summary",
        traces=len(traces),
        session_values=[{
            "cinema": t["cinema"],
            "movie": t["movie"],
            "date": t["date"],
            "session": t["session"],
        } for t in traces],
        direct_tests=len(tests),
        direct_same_path=sum(bool(x.get("same_seat_path")) for x in tests),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
