#!/usr/bin/env python3
"""VIESHOW live session-ID discovery + direct-seat URL spike.

No purchase/reservation/form submission is performed.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

SHOWTIMES_URL = "https://www.vscinemas.com.tw/ShowTimes/"
SHOWTIMES_ENDPOINT = "https://www.vscinemas.com.tw/ShowTimes/ShowTimes/GetShowTimes"
VOUCHER_DEFAULT_URL = "https://sales.vscinemas.com.tw/VoucherTicketing/Default.aspx"
SEAT_URL = "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
CINEMA_CODES = ["TP", "MUC", "NF", "KS"]
USER_SAMPLE = ("21", "165181")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def new_context(browser):
    return browser.new_context(
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 900},
    )


def select_cinema(page, code: str) -> bool:
    selectors = ["#CinemaNameTWInfoF", "#CinemaNameTWInfoS"]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        try:
            info = locator.evaluate(
                """(select, code) => ({
                    visible: !!(select.offsetWidth || select.offsetHeight || select.getClientRects().length),
                    enabled: !select.disabled,
                    hasCode: Array.from(select.options).some(o => (o.value || '').trim() === code)
                })""",
                code,
            )
            if info["hasCode"] and info["visible"] and info["enabled"]:
                locator.select_option(code, timeout=8000)
                page.wait_for_timeout(7000)
                return True
        except Exception as exc:
            emit("select_error", code=code, selector=selector, error=str(exc))

    matched = page.evaluate(
        """async (code) => {
            const selectors = [
                '#CinemaNameTWInfoF', '#CinemaNameTWInfoS',
                '#CinemaNameENInfoF', '#CinemaNameENInfoS'
            ];
            let found = false;
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (!el) continue;
                if (!Array.from(el.options).some(o => (o.value || '').trim() === code)) continue;
                el.value = code;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                found = true;
            }
            return found;
        }""",
        code,
    )
    if matched:
        page.wait_for_timeout(7000)
    return bool(matched)


def inspect_showtimes_endpoint(page, code: str) -> dict:
    return page.evaluate(
        """async (code) => {
            const response = await fetch('/ShowTimes/ShowTimes/GetShowTimes', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: 'CinemaCode=' + encodeURIComponent(code)
            });
            const text = await response.text();
            const doc = new DOMParser().parseFromString(text, 'text/html');

            const timeContainers = Array.from(doc.querySelectorAll('.SessionTimeInfo'));
            const timeDetails = timeContainers.slice(0, 5).map((el) => {
                const descendants = Array.from(el.querySelectorAll('*')).slice(0, 20).map((d) => ({
                    tag: d.tagName,
                    text: (d.textContent || '').trim().slice(0, 120),
                    attrs: Object.fromEntries(Array.from(d.attributes || []).map(a => [a.name, a.value]))
                }));
                return {
                    text: (el.textContent || '').trim().slice(0, 400),
                    attrs: Object.fromEntries(Array.from(el.attributes || []).map(a => [a.name, a.value])),
                    outerHTML: el.outerHTML.slice(0, 2500),
                    descendants
                };
            });

            const interesting = Array.from(doc.querySelectorAll('*'))
                .filter(el => {
                    const html = el.outerHTML || '';
                    return /txtSessionId|SessionId|SessionID|booking\.aspx|cinemacode/i.test(html);
                })
                .slice(0, 20)
                .map(el => el.outerHTML.slice(0, 1800));

            return {
                status: response.status,
                length: text.length,
                contains_txtSessionId: /txtSessionId/i.test(text),
                contains_sessionId: /SessionId/i.test(text),
                contains_booking: /booking\.aspx/i.test(text),
                time_container_count: timeContainers.length,
                time_details: timeDetails,
                interesting
            };
        }""",
        code,
    )


def extract_pairs_from_text(raw: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    patterns = [
        r"booking\.aspx\?[^\"'<>]*?cinemacode=(\d+)[^\"'<>]*?txtSessionId=(\d+)",
        r"cinemacode=(\d+)[^\"'<>]{0,300}?txtSessionId=(\d+)",
    ]
    for pat in patterns:
        for cinema, session in re.findall(pat, raw, flags=re.I):
            pair = (cinema, session)
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def direct_check(browser, cinema: str, session: str, mode: str) -> dict:
    ctx = new_context(browser)
    page = ctx.new_page()
    requested = f"{SEAT_URL}?cinemacode={cinema}&txtSessionId={session}"
    try:
        if mode == "warm_voucher_default":
            page.goto(VOUCHER_DEFAULT_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)
        response = page.goto(requested, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(3500)
        body = page.locator("body").inner_text(timeout=5000)
        result = {
            "cinemacode": cinema,
            "session_id": session,
            "mode": mode,
            "requested_url": requested,
            "status": response.status if response else None,
            "final_url": page.url,
            "title": page.title(),
            "same_session_seat_path": "/voucherticketing/sessionseats.aspx" in page.url.lower(),
            "seatish_elements": page.locator(
                '[id*="seat" i], [class*="seat" i], img[src*="seat" i], '
                '[id*="chair" i], [class*="chair" i]'
            ).count(),
            "body_excerpt": re.sub(r"\s+", " ", body).strip()[:900],
            "error": None,
        }
    except Exception as exc:
        result = {
            "cinemacode": cinema,
            "session_id": session,
            "mode": mode,
            "requested_url": requested,
            "status": None,
            "final_url": page.url,
            "title": "",
            "same_session_seat_path": False,
            "seatish_elements": 0,
            "body_excerpt": "",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        ctx.close()
    return result


def main() -> int:
    discovered: list[tuple[str, str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        ctx = new_context(browser)
        page = ctx.new_page()
        page.goto(SHOWTIMES_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8000)

        initial = page.content()
        if "queue-it" in f"{page.url}\n{initial}".lower():
            raise RuntimeError("VIESHOW source unavailable: Queue-it waiting room")
        if "Access Denied" in initial:
            raise RuntimeError("VIESHOW ShowTimes returned Access Denied")

        for code in CINEMA_CODES:
            ok = select_cinema(page, code)
            emit("cinema_select", code=code, ok=ok)
            if not ok:
                continue

            live_html = page.content()
            live_pairs = extract_pairs_from_text(live_html)
            emit(
                "selected_dom_scan",
                code=code,
                html_length=len(live_html),
                pair_count=len(live_pairs),
                pairs=live_pairs[:10],
                txtSessionId=("txtSessionId" in live_html),
                sessionId=bool(re.search(r"SessionId", live_html, re.I)),
                booking=("booking.aspx" in live_html.lower()),
                sample_session_html=[
                    x[:1800]
                    for x in re.findall(
                        r'<[^>]*class=["\'][^"\']*SessionTimeInfo[^"\']*["\'][\s\S]{0,1800}',
                        live_html,
                        flags=re.I,
                    )[:3]
                ],
            )
            for cinema, session in live_pairs[:2]:
                discovered.append((code, cinema, session))

            api = inspect_showtimes_endpoint(page, code)
            emit("endpoint_scan", code=code, **api)
            api_blob = json.dumps(api, ensure_ascii=False)
            api_pairs = extract_pairs_from_text(api_blob)
            emit("endpoint_pairs", code=code, pair_count=len(api_pairs), pairs=api_pairs[:10])
            for cinema, session in api_pairs[:2]:
                if (code, cinema, session) not in discovered:
                    discovered.append((code, cinema, session))

        ctx.close()

        # Always preserve the user's supplied sample as a control.
        targets = discovered[:8]
        targets.append(("USER", USER_SAMPLE[0], USER_SAMPLE[1]))

        checks = []
        for source_code, cinema, session in targets:
            for mode in ("fresh_context", "warm_voucher_default"):
                result = direct_check(browser, cinema, session, mode)
                checks.append((source_code, result))
                emit("direct_check", source_code=source_code, **result)

        browser.close()

    live = [(src, x) for src, x in checks if src != "USER"]
    fresh = [x for _, x in live if x["mode"] == "fresh_context"]
    warm = [x for _, x in live if x["mode"] == "warm_voucher_default"]
    emit(
        "summary",
        live_pairs_discovered=len(discovered),
        live_unique_pairs=len({(c, s) for _, c, s in discovered}),
        fresh_total=len(fresh),
        fresh_same_path=sum(bool(x["same_session_seat_path"]) for x in fresh),
        warm_total=len(warm),
        warm_same_path=sum(bool(x["same_session_seat_path"]) for x in warm),
    )

    # Diagnostic run succeeds even when the legacy direct URL strategy does not.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
