#!/usr/bin/env python3
"""Live technical spike for VIESHOW per-session direct seat URLs.

This script:
1. Opens the official VIESHOW ShowTimes page in a real Chromium session.
2. Selects several cinema codes and extracts live booking links containing
   cinemacode + txtSessionId.
3. Replays the corresponding VoucherTicketing/SessionSeats.aspx URL in a
   brand-new browser context (no prior cookies), then again after visiting
   VoucherTicketing/Default.aspx.
4. Prints structured JSON so the GitHub Actions log is the evidence.

It does not place orders, reserve seats, or submit any forms.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import sync_playwright


SHOWTIMES_URL = "https://www.vscinemas.com.tw/ShowTimes/"
VOUCHER_DEFAULT_URL = "https://sales.vscinemas.com.tw/VoucherTicketing/Default.aspx"
SEAT_URL = "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"

CINEMA_CODES = ["TP", "MUC", "NF", "KS"]
USER_SAMPLE = {"cinemacode": "21", "session_id": "165181", "source": "user_sample"}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class SessionLink:
    ui_cinema_code: str
    cinemacode: str
    session_id: str
    time_text: str
    booking_url: str
    source: str = "live_showtimes"


@dataclass
class DirectCheck:
    cinemacode: str
    session_id: str
    mode: str
    requested_url: str
    status: int | None
    final_url: str
    title: str
    same_session_seat_path: bool
    seatish_elements: int
    body_excerpt: str
    error: str | None = None


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
        except Exception:
            pass

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
                const hasCode = Array.from(el.options).some(
                    option => (option.value || '').trim() === code
                );
                if (!hasCode) continue;
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


def parse_session_link(ui_code: str, text: str, href: str) -> SessionLink | None:
    absolute = urljoin(SHOWTIMES_URL, href)
    parsed = urlparse(absolute)
    qs = parse_qs(parsed.query)
    cinema = (qs.get("cinemacode") or [""])[0]
    session = (qs.get("txtSessionId") or [""])[0]
    if not cinema or not session:
        return None
    time_match = re.search(r"\b\d{1,2}:\d{2}\b", text or "")
    time_text = time_match.group(0) if time_match else (text or "").strip()[:40]
    return SessionLink(
        ui_cinema_code=ui_code,
        cinemacode=cinema,
        session_id=session,
        time_text=time_text,
        booking_url=absolute,
    )


def extract_live_sessions(page, per_cinema: int = 2) -> list[SessionLink]:
    sessions: list[SessionLink] = []
    for code in CINEMA_CODES:
        ok = select_cinema(page, code)
        print(json.dumps({"event": "cinema_select", "code": code, "ok": ok}, ensure_ascii=False))
        if not ok:
            continue

        raw_links = page.locator('a[href*="booking.aspx"][href*="txtSessionId"]').evaluate_all(
            """els => els.map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.getAttribute('href') || ''
            }))"""
        )

        seen: set[tuple[str, str]] = set()
        added = 0
        for item in raw_links:
            parsed = parse_session_link(code, item.get("text", ""), item.get("href", ""))
            if parsed is None:
                continue
            key = (parsed.cinemacode, parsed.session_id)
            if key in seen:
                continue
            seen.add(key)
            sessions.append(parsed)
            added += 1
            if added >= per_cinema:
                break

        print(
            json.dumps(
                {
                    "event": "sessions_extracted",
                    "ui_cinema_code": code,
                    "count": added,
                    "sessions": [asdict(s) for s in sessions if s.ui_cinema_code == code],
                },
                ensure_ascii=False,
            )
        )
    return sessions


def build_seat_url(cinema: str, session: str) -> str:
    return f"{SEAT_URL}?cinemacode={cinema}&txtSessionId={session}"


def inspect_direct_url(browser, cinema: str, session: str, mode: str) -> DirectCheck:
    context = browser.new_context(
        locale="zh-TW",
        timezone_id="Asia/Taipei",
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 900},
    )
    page = context.new_page()
    requested = build_seat_url(cinema, session)

    try:
        if mode == "warm_voucher_default":
            page.goto(VOUCHER_DEFAULT_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)

        response = page.goto(requested, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(4000)

        status = response.status if response else None
        final_url = page.url
        title = page.title()
        try:
            body = page.locator("body").inner_text(timeout=5000)
        except Exception:
            body = ""

        seatish_elements = page.locator(
            '[id*="seat" i], [class*="seat" i], img[src*="seat" i], '
            '[id*="chair" i], [class*="chair" i]'
        ).count()

        same_path = "/voucherticketing/sessionseats.aspx" in final_url.lower()
        excerpt = re.sub(r"\s+", " ", body).strip()[:1200]

        return DirectCheck(
            cinemacode=cinema,
            session_id=session,
            mode=mode,
            requested_url=requested,
            status=status,
            final_url=final_url,
            title=title,
            same_session_seat_path=same_path,
            seatish_elements=seatish_elements,
            body_excerpt=excerpt,
        )
    except Exception as exc:
        return DirectCheck(
            cinemacode=cinema,
            session_id=session,
            mode=mode,
            requested_url=requested,
            status=None,
            final_url=page.url,
            title="",
            same_session_seat_path=False,
            seatish_elements=0,
            body_excerpt="",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        context.close()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)

        source_context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
        )
        source_page = source_context.new_page()
        source_page.goto(SHOWTIMES_URL, wait_until="domcontentloaded", timeout=60_000)
        source_page.wait_for_timeout(8000)

        initial = source_page.content()
        if "queue-it" in f"{source_page.url}\n{initial}".lower():
            raise RuntimeError("VIESHOW source unavailable: Queue-it waiting room")
        if "Access Denied" in initial:
            raise RuntimeError("VIESHOW ShowTimes returned Access Denied")

        sessions = extract_live_sessions(source_page, per_cinema=2)
        source_context.close()

        test_targets = sessions[:]
        test_targets.append(
            SessionLink(
                ui_cinema_code="MUC",
                cinemacode=USER_SAMPLE["cinemacode"],
                session_id=USER_SAMPLE["session_id"],
                time_text="",
                booking_url="",
                source=USER_SAMPLE["source"],
            )
        )

        checks: list[DirectCheck] = []
        for target in test_targets:
            for mode in ("fresh_context", "warm_voucher_default"):
                check = inspect_direct_url(
                    browser,
                    target.cinemacode,
                    target.session_id,
                    mode,
                )
                checks.append(check)
                print(
                    json.dumps(
                        {"event": "direct_check", **asdict(check), "source": target.source},
                        ensure_ascii=False,
                    )
                )

        browser.close()

    live_checks = [
        c for c in checks
        if any(s.source == "live_showtimes" and s.cinemacode == c.cinemacode and s.session_id == c.session_id
               for s in test_targets)
    ]
    fresh_live = [c for c in live_checks if c.mode == "fresh_context"]
    warm_live = [c for c in live_checks if c.mode == "warm_voucher_default"]

    summary = {
        "event": "summary",
        "live_sessions_extracted": len(sessions),
        "cinemas_with_sessions": sorted({s.ui_cinema_code for s in sessions}),
        "fresh_same_path": sum(c.same_session_seat_path for c in fresh_live),
        "fresh_total": len(fresh_live),
        "warm_same_path": sum(c.same_session_seat_path for c in warm_live),
        "warm_total": len(warm_live),
        "fresh_http_ok": sum((c.status or 999) < 400 for c in fresh_live),
        "warm_http_ok": sum((c.status or 999) < 400 for c in warm_live),
    }
    print(json.dumps(summary, ensure_ascii=False))

    # The spike itself should fail only if no live session could be extracted.
    # Direct-seat failures are evidence, not infrastructure failures.
    return 0 if sessions else 2


if __name__ == "__main__":
    raise SystemExit(main())
