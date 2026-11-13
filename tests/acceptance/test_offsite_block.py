#!/usr/bin/env python
"""Fix 3, offline test: the agent's browser context blocks off-site requests and tabs.

Part 1 (no browser): unit-test browser_tools.is_allowed_url against the allowlist spec.
Part 2 (local only, no model, no internet): loopback http.server on 127.0.0.1 —
  - a request to it through the agent's context must be aborted (server sees nothing)
  - a popup to it must be closed, leaving the original page active
  - each block is logged as one line in the existing logs/network.jsonl

Run:  .venv/bin/python tests/acceptance/test_offsite_block.py
Exit 0 = all checks held; nonzero = the wall leaks somewhere.
"""
import asyncio
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from browser_tools import _S, _start, close_browser, is_allowed_url  # noqa: E402

# (url, allowed?, note)
URL_CASES = [
    ("https://saucedemo.com/", True, "canonical host"),
    ("https://www.saucedemo.com/inventory.html", True, "www host, protected page"),
    ("http://saucedemo.com/", True, "http allowed per spec"),
    ("https://example.com", False, "other host"),
    ("https://saucedemo.com.evil.com", False, "saucedemo.com as evil's subdomain"),
    ("https://evil.com/saucedemo.com", False, "saucedemo.com only in path"),
    ("https://www.saucedemo.com@evil.com/", False, "userinfo trick: real host is evil.com"),
    ("about:blank", True, "non-network scheme"),
    ("data:text/html,<h1>hi</h1>", True, "non-network scheme"),
    ("blob:https://www.saucedemo.com/8a1e-4b", True, "non-network scheme"),
    ("file:///etc/passwd", False, "file scheme"),
    ("https://shop.saucedemo.com/", False, "unlisted subdomain (exact hosts only)"),
]

SERVED = {"hits": 0}


class _Probe(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SERVED["hits"] += 1  # must stay 0: Playwright aborts before the wire
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"offsite-probe")

    def log_message(self, *a):
        pass


async def live_checks(port, failures):
    import browser_tools as bt
    await bt._start()  # the agent's context: route wall + popup guard, no session
    page = _S["page"]
    offsite = f"http://127.0.0.1:{port}/blocked-probe"

    # 1. popup to loopback must be closed; original page stays the active one
    #    (run this FIRST: an aborted main-frame goto swaps Chromium to its
    #    chrome-error:// page, where evaluate no longer works)
    async with page.context.expect_page() as pop_info:
        await page.evaluate(f"window.open({offsite!r})")
    popup = await pop_info.value
    for _ in range(100):
        if popup.is_closed():
            break
        await asyncio.sleep(0.1)
    closed, main_alive = popup.is_closed(), not page.is_closed()
    if not closed:
        failures.append("off-site popup was not closed")
    if not main_alive:
        failures.append("original page was closed by the popup guard")
    print(f"  [{'PASS' if closed else 'FAIL'}] off-site popup closed by guard")
    print(f"  [{'PASS' if main_alive else 'FAIL'}] original page still open/active")

    # 2. main-page navigation to loopback must be aborted, page stays on its site
    try:
        await page.goto(offsite, wait_until="commit")
        aborted = "127.0.0.1" not in page.url
    except Exception:
        aborted = "127.0.0.1" not in page.url
    if not aborted:
        failures.append(f"main-page goto to {offsite} was not aborted (now at {page.url})")
    print(f"  [{'PASS' if aborted else 'FAIL'}] main-page goto to 127.0.0.1 aborted "
          f"(page now at {page.url!r}, not the offsite URL)")

    await close_browser()

    # 3. every block landed as one line in the existing log (no new files)
    log = ROOT / "logs/network.jsonl"
    blocked = [json.loads(l) for l in log.read_text().splitlines()[-20:]
               if '"blocked": true' in l or '"blocked":true' in l]
    hits = [e for e in blocked if "127.0.0.1" in e.get("url", "")]
    ok = len(hits) >= 2 and SERVED["hits"] == 0
    if not ok:
        failures.append(f"expected >=2 blocked log lines for 127.0.0.1 and 0 served requests; "
                        f"got {len(hits)} blocked lines, {SERVED['hits']} served")
    print(f"  [{'PASS' if ok else 'FAIL'}] blocked requests logged to logs/network.jsonl "
          f"({len(hits)} lines); server received {SERVED['hits']} requests")


def main():
    failures = []
    print("=== is_allowed_url unit cases ===")
    for url, want, note in URL_CASES:
        got = is_allowed_url(url)
        mark = "PASS" if got == want else "FAIL"
        if got != want:
            failures.append(f"is_allowed_url({url!r}): expected {want}, got {got}")
        print(f"  [{mark}] {'allow' if got else 'BLOCK'} {url!r:<45} ({note})")

    print("=== live loopback checks (local http.server, no internet) ===")
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Probe) as srv:
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            asyncio.run(live_checks(port, failures))
        finally:
            srv.shutdown()
            srv.server_close()

    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILURES")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: all off-site block checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
