from __future__ import annotations

import json
import unittest

from playwright.sync_api import sync_playwright


class BroadwayBuyLinkProbe(unittest.TestCase):
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
            page.wait_for_timeout(8000)
            result = page.evaluate(
                """async () => {
                  const scripts = [...document.querySelectorAll('script[src]')]
                    .map(s => new URL(s.src, location.href).href);
                  const hits = [];
                  for (const src of scripts) {
                    try {
                      const text = await (await fetch(src)).text();
                      for (const needle of ['quick-view.html', 'GetMovieList', 'BUY TICKET', 'buyTicket', 'book.html', 'Login']) {
                        let idx = text.indexOf(needle);
                        if (idx >= 0) {
                          hits.push({src, needle, snippet: text.slice(Math.max(0, idx - 900), idx + 1800)});
                        }
                      }
                    } catch (e) {}
                  }
                  const timeNodes = [...document.querySelectorAll('*')]
                    .filter(el => /^\\d{1,2}:\\d{2}$/.test((el.textContent || '').trim()))
                    .slice(0, 8)
                    .map(el => {
                      let p = el;
                      for (let i = 0; i < 4 && p.parentElement; i++) p = p.parentElement;
                      return p.outerHTML.slice(0, 6000);
                    });
                  return {url: location.href, scripts, hits, timeNodes};
                }"""
            )
            print("BROADWAY_BUY_PROBE " + json.dumps(result, ensure_ascii=False))
            context.close()
            browser.close()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
