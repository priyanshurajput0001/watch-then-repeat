#!/usr/bin/env python
"""QA audit, task 8: compare the product's route-based network logging against a
page.on("request") listener for the SAME run.

Runs the recorded checkout flow once with BOTH:
  - ctx.route("**/*", browser_tools._route)  (product interception, logs to logs/network.jsonl
    iff the *route-time* page URL contains "/checkout-")
  - a request listener + framenavigated tracker (ground truth: what was requested, and on
    which committed page)

Then classifies, for every request: expected-checkout (own URL or hosting page URL contains
"/checkout-"), and diffs against the product's log slice -> missed / unrelated.

Run: .venv/bin/python tests/acceptance/test_network_interception.py
Does its own fresh login; writes reports/evidence/audit8_network_*.json; appends the
product-route slice to logs/network.jsonl exactly as a real replay would.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import browser_tools as bt
from playwright.async_api import async_playwright

NETLOG = ROOT / "logs/network.jsonl"


async def main():
    listener = []          # ground truth
    committed = {"url": ""}

    async with async_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        browser = await pw.chromium.launch()
        ctx = await browser.new_context()
        await ctx.route("**/*", bt._route)          # product interception, verbatim
        page = await ctx.new_page()
        bt._S["page"] = page                        # _route reads bt._S["page"].url
        page.set_default_timeout(10_000)

        def on_request(r):
            listener.append({"t": time.time(), "req_url": r.url, "method": r.method,
                             "type": r.resource_type, "page_url_at_event": page.url,
                             "committed_page": committed["url"]})

        def on_nav(frame):
            if frame is page.main_frame:
                committed["url"] = frame.url

        page.on("request", on_request)
        page.on("framenavigated", on_nav)

        pre = NETLOG.read_text().splitlines() if NETLOG.exists() else []

        await page.goto("https://www.saucedemo.com/")
        await page.get_by_test_id("username").fill("standard_user")
        await page.get_by_test_id("password").fill("secret_sauce")
        await page.get_by_test_id("login-button").click()
        await page.wait_for_url("**/inventory.html")
        await page.get_by_test_id("product-sort-container").select_option("lohi")
        await page.get_by_test_id("add-to-cart-sauce-labs-onesie").click()
        await page.get_by_test_id("add-to-cart-sauce-labs-bike-light").click()
        await page.get_by_test_id("shopping-cart-link").click()
        await page.get_by_test_id("checkout").click()
        await page.get_by_test_id("firstName").fill("Test")
        await page.get_by_test_id("lastName").fill("User")
        await page.get_by_test_id("postalCode").fill("12345")
        await page.get_by_test_id("continue").click()
        await page.get_by_test_id("total-label").wait_for(state="visible")
        await page.get_by_test_id("finish").click()
        await page.get_by_test_id("complete-header").wait_for(state="visible")
        await browser.close()

    post = NETLOG.read_text().splitlines() if NETLOG.exists() else []
    product_slice = [json.loads(l) for l in post[len(pre):]]

    def checkout_phase(req):
        return ("/checkout-" in req["req_url"]) or ("/checkout-" in req["committed_page"])

    expected = [r for r in listener if checkout_phase(r)]
    exp_urls = [r["req_url"] for r in expected]
    prod_urls = [e["url"] for e in product_slice]
    missed = [u for u in exp_urls if u not in prod_urls]
    unrelated = [u for u in prod_urls if u not in exp_urls]

    report = {
        "listener_requests_total": len(listener),
        "product_route_logged": len(product_slice),
        "expected_checkout_phase": len(expected),
        "missed_by_product_route": missed,
        "logged_but_not_checkout_phase": unrelated,
        "product_slice": product_slice,
        "expected_detail": expected,
        "all_listener_requests": listener,
        "note": "product gate = page URL at ROUTE time (= source page, navigation target not yet "
                "committed); a document request TO a checkout page from a non-checkout page is missed",
    }
    out = ROOT / "reports/evidence/audit8_network_comparison.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ("product_slice", "expected_detail")}, indent=2))
    print(f"evidence -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
