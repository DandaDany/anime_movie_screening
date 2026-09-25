#!/usr/bin/env python3
"""Check whether VIESHOW quick-booking APIs are reachable without Playwright."""
from __future__ import annotations
import json
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

TESTS = [
    ("cinemas", "https://www.vscinemas.com.tw/api/GetLstDicCinema"),
    ("movies_tp", "https://www.vscinemas.com.tw/api/GetLstDicMovie?cinema=" + urllib.parse.quote("1|TP")),
    ("dates_tp", "https://www.vscinemas.com.tw/api/GetLstDicDate?cinema=" + urllib.parse.quote("1|TP") + "&movie=HO00017914"),
    ("sessions_tp", "https://www.vscinemas.com.tw/api/GetLstDicSession?cinema=" + urllib.parse.quote("1|TP") + "&movie=HO00017914&date=" + urllib.parse.quote("2026/10/31")),
]


def main():
    ok = True
    for label, url in TESTS:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.vscinemas.com.tw/",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw)
                print(json.dumps({
                    "label": label,
                    "status": resp.status,
                    "url": url,
                    "type": type(parsed).__name__,
                    "count": len(parsed) if isinstance(parsed, list) else None,
                    "sample": parsed[:3] if isinstance(parsed, list) else parsed,
                }, ensure_ascii=False), flush=True)
        except Exception as exc:
            ok = False
            print(json.dumps({
                "label": label,
                "url": url,
                "error": f"{type(exc).__name__}: {exc}",
            }, ensure_ascii=False), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
