#!/usr/bin/env python3
"""Inspect VIESHOW quick-booking selects and discover live session IDs."""

from __future__ import annotations
import json
from playwright.sync_api import sync_playwright

HOME = "https://www.vscinemas.com.tw/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def emit(event, **data):
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def dump_selects(page, label):
    rows = page.locator("select").evaluate_all(
        """sels => sels.map((s, i) => ({
            index: i,
            id: s.id || '',
            name: s.name || '',
            className: s.className || '',
            visible: !!(s.offsetWidth || s.offsetHeight || s.getClientRects().length),
            value: s.value || '',
            optionCount: s.options.length,
            options: Array.from(s.options).slice(0, 12).map(o => ({
                value: (o.value || '').trim(),
                text: (o.textContent || '').trim(),
                disabled: !!o.disabled
            }))
        }))"""
    )
    emit("select_dump", label=label, selects=rows)
    return rows


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        ctx = browser.new_context(
            locale="zh-TW", timezone_id="Asia/Taipei", user_agent=UA,
            viewport={"width": 1366, "height": 900}
        )
        page = ctx.new_page()

        requests = []
        page.on(
            "request",
            lambda req: requests.append({
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type,
                "post_data": req.post_data,
            }) if req.resource_type in ("xhr", "fetch") else None,
        )

        page.goto(HOME, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(7000)
        rows = dump_selects(page, "initial")

        # Try each visible select that already has a non-empty enabled option.
        # After each change we only inspect resulting state; no submit/button click.
        for row in rows:
            if not row["visible"]:
                continue
            opts = [o for o in row["options"] if o["value"] and not o["disabled"]]
            if not opts:
                continue

            selector = f"select#{row['id']}" if row["id"] else f"select:nth-of-type({row['index'] + 1})"
            try:
                loc = page.locator(selector)
                before = len(requests)
                loc.select_option(opts[0]["value"], timeout=8000)
                page.wait_for_timeout(3500)
                emit(
                    "select_action",
                    selector=selector,
                    chosen=opts[0],
                    new_requests=requests[before:],
                )
                dump_selects(page, f"after_{row['id'] or row['index']}")
            except Exception as exc:
                emit("select_action_error", selector=selector, error=f"{type(exc).__name__}: {exc}")

        emit(
            "interesting_requests",
            requests=[
                r for r in requests
                if any(k in r["url"].lower() for k in ("session", "ticket", "cinema", "movie", "show"))
            ][-80:]
        )

        ctx.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
