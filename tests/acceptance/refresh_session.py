#!/usr/bin/env python
"""QA audit helper: refresh artifacts/state.json via a scripted login (no model),
then VERIFY it is logged-in with an EMPTY cart. Mirrors recorder.py's save point
(right after login, before any cart change) without rewriting any tracked file.

Run: .venv/bin/python tests/acceptance/refresh_session.py [--check-only]
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "artifacts/state.json"
START = "https://www.saucedemo.com/"
INVENTORY = "https://www.saucedemo.com/inventory.html"


async def check(pw):
    """Load ONLY the state file (no login) and verify: logged in, cart empty."""
    browser = await pw.chromium.launch()
    ctx = await browser.new_context(storage_state=str(STATE))
    page = await ctx.new_page()
    await page.goto(INVENTORY, wait_until="domcontentloaded")
    landed = page.url
    on_login = await page.get_by_test_id("login-button").count()
    badge = await page.get_by_test_id("shopping-cart-badge").count()
    cart_ls = await page.evaluate("localStorage.getItem('cart-contents')")
    cookie = next((c for c in await ctx.cookies() if c["name"] == "session-username"), None)
    await browser.close()
    return {"landed_url": landed, "on_login_form": on_login, "badge_count": badge,
            "cart_localstorage": cart_ls,
            "cookie_expires_epoch": cookie["expires"] if cookie else None,
            "now_epoch": time.time()}


async def main():
    check_only = "--check-only" in sys.argv
    async with async_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        if not check_only:
            browser = await pw.chromium.launch()
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(START)
            await page.get_by_test_id("username").fill("standard_user")
            await page.get_by_test_id("password").fill("secret_sauce")
            await page.get_by_test_id("login-button").click()
            await page.wait_for_url("**/inventory.html")
            STATE.parent.mkdir(exist_ok=True)
            await ctx.storage_state(path=str(STATE))  # same save point as recorder.py
            await browser.close()
            print(f"state refreshed -> {STATE}")
        r = await check(pw)
    r["cookie_valid_seconds_left"] = (r["cookie_expires_epoch"] - r["now_epoch"]) if r["cookie_expires_epoch"] else None
    ok = (r["on_login_form"] == 0 and r["badge_count"] == 0 and r["cart_localstorage"] is None
          and r["landed_url"].endswith("/inventory.html"))
    r["VERDICT"] = "logged-in, cart EMPTY" if ok else "PROBLEM"
    print(json.dumps(r, indent=2))
    out = ROOT / f"reports/evidence/audit3_state_check{'_checkonly' if check_only else ''}.json"
    out.write_text(json.dumps(r, indent=2))
    print(f"evidence -> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
