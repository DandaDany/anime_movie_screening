#!/usr/bin/env python3
"""A/B raw HTTP access to VIESHOW public SessionSeats.

Read-only. Confirms whether Referer alone is sufficient without browser state.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

SEAT_URL = (
    "https://sales.vscinemas.com.tw/VoucherTicketing/SessionSeats.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
HOME = "https://www.vscinemas.com.tw/"
BOOKING = (
    "https://www.vscinemas.com.tw/vsTicketing/ticketing/booking.aspx"
    "?cinemacode=1&txtSessionId=1878613"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def emit(event: str, **data) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def fetch(label: str, referer: str | None) -> dict:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    if referer:
        headers["Referer"] = referer

    req = urllib.request.Request(SEAT_URL, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())

    try:
        with opener.open(req, timeout=30) as resp:
            raw = resp.read()
            status = resp.status
            location = resp.headers.get("Location")
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        location = exc.headers.get("Location")
        content_type = exc.headers.get("Content-Type", "")

    text = raw.decode("utf-8", errors="replace")
    if "charset=big5" in content_type.lower() or "charset=950" in content_type.lower():
        text = raw.decode("big5", errors="replace")

    result = {
        "label": label,
        "referer": referer,
        "status": status,
        "location": location,
        "content_type": content_type,
        "bytes": len(raw),
        "has_grid": 'id="GridViewSessionSeats"' in text,
        "has_preview_title": "場次座位預覽" in text,
        "available_markers": len(re.findall(r'label label-info', text, flags=re.I)),
        "sold_markers": len(re.findall(r'label label-danger', text, flags=re.I)),
        "wheelchair_markers": len(re.findall(r'wheelchair_available', text, flags=re.I)),
        "sample": re.sub(r"\s+", " ", text)[:500],
    }
    emit("raw_http", **result)
    return result


def main() -> int:
    cases = [
        fetch("A_no_referer", None),
        fetch("B_home_referer", HOME),
        fetch("C_booking_referer", BOOKING),
    ]

    success = (
        not cases[0]["has_grid"]
        and cases[1]["status"] == 200
        and cases[1]["has_grid"]
        and cases[2]["status"] == 200
        and cases[2]["has_grid"]
    )
    emit(
        "summary",
        success=success,
        cases=[
            {
                "label": c["label"],
                "status": c["status"],
                "location": c["location"],
                "has_grid": c["has_grid"],
                "available_markers": c["available_markers"],
                "sold_markers": c["sold_markers"],
            }
            for c in cases
        ],
    )
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
