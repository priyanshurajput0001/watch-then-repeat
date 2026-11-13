#!/usr/bin/env python
"""QA audit, Phase 2.4: do the recorded locators survive a layout change?

Drives a scripted saucedemo run (no model) and, at each step's pre-action state,
resolves the step's Locator + Fallback lines from the recorded skill. The whole run is
repeated under route-interception HTML rewrites (presentational changes only):

  baseline      - untouched pages (sanity)
  strip_class   - every class="..." attribute removed
  wrap_body     - body content wrapped in an extra <div> (extra DOM level)
  reorder_items - the inventory list DOM reversed (products in opposite order)
  all_combined  - all three rewrites at once

Each scenario ASSERTS its rewrite was actually served (no vacuous pass). A locator
"survives" if it resolves to exactly 1 element; 0 = broken; >1 = strict-mode hazard.

Run:  .venv/bin/python tests/acceptance/test_locator_resilience.py
Requires a fresh artifacts/state.json (saucedemo session cookie lives ~10 min; if the
harness reports "landed on login", re-run recorder.py and retry immediately).
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/saucedemo_checkout.md"
STATE = ROOT / "artifacts/state.json"

START = "https://www.saucedemo.com/"
INVENTORY = "https://www.saucedemo.com/inventory.html"


# ------------------------------------------------------------ HTML rewrites
def strip_class(html):
    return re.sub(r'\sclass="[^"]*"', "", html)


def wrap_body(html):
    return html.replace("<body", "<body data-audit-wrap='outer'><div data-audit-wrap='inner'>", 1) \
               .replace("</body>", "</div></body>", 1)


def reorder_items(html):
    m = re.search(r'(<div[^>]*data-test="inventory-list"[^>]*>)(.*?)(</div>\s*</div>\s*</div>)',
                  html, flags=re.S)
    if not m:
        return html
    bodytxt = m.group(2)
    items = re.findall(r'<div[^>]*data-test="inventory-item".*?(?=<div[^>]*data-test="inventory-item"|\Z)',
                       bodytxt, flags=re.S)
    if len(items) < 2:
        return html
    return html[:m.start(2)] + "".join(reversed(items)) + html[m.end(2):]


SCENARIOS = {
    "baseline": (lambda h: h, None),
    "strip_class": (strip_class, "document.querySelectorAll('[class]').length === 0"),
    "wrap_body": (wrap_body, "document.querySelector('body > div[data-audit-wrap=\"inner\"]') != null"),
    "reorder_items": (reorder_items, None),  # verified via first-item title vs baseline
    "all_combined": (lambda h: reorder_items(wrap_body(strip_class(h))),
                     "document.querySelector('body > div[data-audit-wrap=\"inner\"]') != null "
                     "&& document.querySelectorAll('[class]').length === 0"),
}


def parse_locator_lines(md_text):
    out = []
    step = None
    for line in md_text.splitlines():
        m = re.match(r"^(\d+)\. ", line)
        if m:
            step = int(m.group(1))
        m = re.match(
            r'^   - (Locator|Fallback): `page\.(get_by_test_id|get_by_role|get_by_label'
            r'|get_by_placeholder|get_by_text|locator)\((.*)\)`$', line)
        if m and step is not None:
            val = re.search(r'"([^"]*)"', m.group(3))
            name = re.search(r'name="([^"]*)"', m.group(3))
            out.append((step, m.group(1), m.group(2),
                        val.group(1) if val else "", name.group(1) if name else ""))
    return out


def loc(page, kind, value, name=""):
    if kind == "get_by_test_id":
        return page.get_by_test_id(value)
    if kind == "get_by_role":
        return page.get_by_role(value, name=name or None, exact=True)
    if kind == "get_by_label":
        return page.get_by_label(value, exact=True)
    if kind == "get_by_placeholder":
        return page.get_by_placeholder(value, exact=True)
    if kind == "get_by_text":
        return page.get_by_text(value, exact=True)
    return page.locator(value)


def make_route_handler(rewrite):
    async def route_handler(route):
        try:
            host = urlparse(route.request.url).hostname or ""
            if not (host == "saucedemo.com" or host.endswith(".saucedemo.com")):
                await route.abort()  # hermetic harness: no fonts/beacons
                return
            resp = await route.fetch()
            ct = resp.headers.get("content-type", "")
            if "text/html" in ct:
                body = rewrite(await resp.text())
                h = {k: v for k, v in resp.headers.items() if k.lower() != "content-encoding"}
                h["content-length"] = str(len(body.encode("utf-8")))
                await route.fulfill(response=resp, body=body, headers=h)
            else:
                await route.fulfill(response=resp)
        except Exception:
            try:
                await route.abort()
            except Exception:
                pass
    return route_handler


async def main():
    if not STATE.exists():
        print("FATAL: artifacts/state.json missing - run recorder.py first")
        return 2
    md = SKILL.read_text()
    by_step = {}
    for step, role, kind, val, name in parse_locator_lines(md):
        by_step.setdefault(step, []).append((role, kind, val, name))

    async with async_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        browser = await pw.chromium.launch()

        results = {}
        for scen, (rewrite, assert_js) in SCENARIOS.items():
            ctx = await browser.new_context(storage_state=str(STATE))
            await ctx.route("**/*", make_route_handler(rewrite))
            page = await ctx.new_page()
            page.set_default_timeout(6000)
            res = {}          # step -> [(role, kind, value, n)]
            note = ""
            try:
                # ---- steps 1-3: login form is reachable at START regardless of session
                await page.goto(START, wait_until="domcontentloaded")
                if await page.get_by_test_id("username").count() != 1:
                    raise RuntimeError(f"landed on {page.url!r} without a login form - "
                                       "state.json expired? re-run recorder.py and retry fast")
                for n in (1, 2, 3):
                    res[n] = [(r, k, v, await loc(page, k, v, nm).count())
                              for r, k, v, nm in by_step[n]]
                # prove login form rewrite: strip_class must have removed classes
                if assert_js:
                    got = await page.evaluate(assert_js)
                    if not got:
                        raise RuntimeError(f"scenario {scen}: rewrite NOT served (assert {assert_js!r} false)")

                # ---- step 4: inventory, before selecting sort
                await page.goto(INVENTORY, wait_until="domcontentloaded")
                await page.get_by_test_id("product-sort-container").wait_for(state="visible")
                res[4] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[4]]
                await page.get_by_test_id("product-sort-container").select_option("lohi")
                await page.get_by_test_id("inventory-item").first.wait_for(state="visible")
                await page.wait_for_timeout(300)  # let React finish reordering the list
                first_before = await page.locator('[data-test="inventory-item"]').first.inner_text()

                # ---- steps 5,6: before each add-to-cart click
                await page.get_by_test_id("shopping-cart-link").wait_for(state="attached")
                res[5] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[5]]
                await page.get_by_test_id("add-to-cart-sauce-labs-onesie").click()
                res[6] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[6]]
                await page.get_by_test_id("add-to-cart-sauce-labs-bike-light").click()

                # prove reorder_items really reversed the DOM (compare POST-sort first items)
                if scen == "baseline":
                    globals()["_BASE_FIRST"] = first_before
                if scen in ("reorder_items", "all_combined"):
                    if first_before == globals().get("_BASE_FIRST"):
                        raise RuntimeError(f"scenario {scen}: reorder rewrite NOT served "
                                           f"(first item still {first_before[:40]!r})")

                # ---- step 7,8: cart page with 2 items
                await page.get_by_test_id("shopping-cart-link").click()
                await page.get_by_test_id("continue-shopping").wait_for(state="visible")  # cart-unique anchor
                res[7] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[7]]
                res[8] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[8]]
                await page.get_by_test_id("checkout").click()

                # ---- steps 9-12: checkout form
                await page.get_by_test_id("checkout-info-container").wait_for(state="visible")
                res[9] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[9]]
                res[10] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[10]]
                res[11] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[11]]
                res[12] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[12]]
                await page.get_by_test_id("firstName").fill("Test")
                await page.get_by_test_id("lastName").fill("User")
                await page.get_by_test_id("postalCode").fill("12345")
                await page.get_by_test_id("continue").click()

                # ---- steps 13,14: overview
                await page.get_by_test_id("checkout-summary-container").wait_for(state="visible")
                res[13] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[13]]
                res[14] = [(r, k, v, await loc(page, k, v, nm).count()) for r, k, v, nm in by_step[14]]
                results[scen] = res
                print(f"  scenario {scen}: completed", flush=True)
            except Exception as e:
                results[scen] = res
                note = f"{type(e).__name__}: {e}"
                print(f"  scenario {scen}: FAILED at step-page resolution: {note}", flush=True)
            finally:
                try:
                    await ctx.unroute_all(behavior="ignoreErrors")
                except Exception:
                    pass
                await ctx.close()
        await browser.close()

    # ---------------- report ----------------
    print(f"\nper-step resolution counts (Locator then Fallbacks, L/F markers):")
    header = f"{'step':<6}" + "".join(f"{sc:<13}" for sc in SCENARIOS)
    print(header)
    all_steps = sorted({n for r in results.values() for n in r})
    for n in all_steps:
        cells = []
        for scen in SCENARIOS:
            cells.append(" ".join(f"{role[0]}:{cnt}" for role, _, _, cnt in results.get(scen, {}).get(n, [])))
        print(f"{n:<6}" + "".join(f"{c:<13}" for c in cells))
    print("(L = primary Locator, F = Fallback; count 1 = unique, 0 = broken, >1 = strict-mode hazard)")

    # JSON evidence
    out = ROOT / "reports/evidence/locator_resilience.json"
    out.write_text(json.dumps({s: {str(n): [list(x) for x in r] for n, r in res.items()}
                               for s, res in results.items()}, indent=2))
    print(f"evidence: {out}")

    # verdict
    ok = True
    for scen in SCENARIOS:
        for n, entries in results.get(scen, {}).items():
            role, kind, val, cnt = entries[0]  # primary
            if cnt != 1:
                print(f"  PROBLEM {scen} step {n}: primary {kind}({val!r}) -> {cnt}")
                ok = False
    baseline_all = [cnt for entries in results.get("baseline", {}).values() for *_, cnt in entries]
    multi = sum(1 for c in baseline_all if c > 1)
    zero = sum(1 for c in baseline_all if c == 0)
    print(f"\nbaseline fallbacks: {multi} resolve to >1 (strict-mode hazard), {zero} resolve to 0")
    print("VERDICT:", "PRIMARY locators survive all rewrites" if ok else "PRIMARY locators BROKEN somewhere")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
