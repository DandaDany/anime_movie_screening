from __future__ import annotations

import json
import unittest

from playwright.sync_api import sync_playwright


class BookingJavascriptProbe(unittest.TestCase):
    def test_dump_booking_javascript(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="zh-TW",
                timezone_id="Asia/Taipei",
                user_agent="Mozilla/5.0 AppleWebKit/537.36 Chrome/126 Safari/537.36",
            )
            page = context.new_page()
            page.goto(
                "https://www.broadway-cineplex.com.tw/book.html?obj=Zhubei",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_timeout(5000)
            broadway = page.evaluate(
                """async () => {
                  const src = [...document.querySelectorAll('script[src]')]
                    .map(s => new URL(s.src, location.href).href)
                    .find(x => x.includes('/js/book.js'));
                  if (!src) return {error: 'book.js missing'};
                  const text = await (await fetch(src)).text();
                  const idx = text.indexOf('bookseat: function');
                  return {src, snippet: idx >= 0 ? text.slice(idx, idx + 9500) : text.slice(0, 9500)};
                }"""
            )
            print("BROADWAY_BOOKSEAT_PROBE " + json.dumps(broadway, ensure_ascii=False))

            try:
                page.goto(
                    "https://www.miranewcinemas.com/Booking/Timetable",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_timeout(5000)
                miranew = page.evaluate(
                    """async () => {
                      const scripts = [...document.querySelectorAll('script')];
                      const results = [];
                      for (const script of scripts) {
                        let text = script.src ? '' : (script.textContent || '');
                        let src = script.src ? new URL(script.src, location.href).href : 'inline';
                        if (script.src) {
                          try { text = await (await fetch(src)).text(); } catch (e) { continue; }
                        }
                        for (const needle of ['SessionId', 'SessionID', 'CinemaList', '/Booking/', 'booking']) {
                          const idx = text.indexOf(needle);
                          if (idx >= 0) {
                            results.push({src, needle, snippet: text.slice(Math.max(0, idx - 1200), idx + 5000)});
                          }
                        }
                      }
                      return results.slice(0, 20);
                    }"""
                )
                print("MIRANEW_BOOKING_PROBE " + json.dumps(miranew, ensure_ascii=False))
            except Exception as exc:
                print("MIRANEW_BOOKING_PROBE_ERROR " + repr(exc))

            context.close()
            browser.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
