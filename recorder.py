"""Watch once: drive the saucedemo checkout with sync Playwright, save artifacts/steps.json + state.json."""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://www.saucedemo.com"
STEPS = Path("artifacts/steps.json")
STATE = Path("artifacts/state.json")


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def record() -> dict:
    """Run the full checkout once. Saves the logged-in (empty-cart) session and the step script."""
    with sync_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        browser = pw.chromium.launch(headless=False)
        page = browser.new_context().new_page()
        page.set_default_timeout(10_000)

        # 1-2: fresh login
        page.goto(BASE)
        page.get_by_test_id("username").fill("standard_user")
        page.get_by_test_id("password").fill("secret_sauce")
        page.get_by_test_id("login-button").click()
        page.wait_for_url("**/inventory.html")
        _check(page.get_by_test_id("title").inner_text() == "Products", "no Products header after login")

        # 3: sort by price (low to high)
        page.get_by_test_id("product-sort-container").select_option("lohi")
        prices = page.get_by_test_id("inventory-item-price").all_inner_texts()
        floats = [float(p.strip().replace("$", "")) for p in prices]
        _check(floats == sorted(floats) and floats[0] == 7.99, f"bad sort order: {floats}")

        # 4: the two cheapest
        names = page.get_by_test_id("inventory-item-name").all_inner_texts()
        _check(names[:2] == ["Sauce Labs Onesie", "Sauce Labs Bike Light"], f"unexpected top items: {names[:2]}")

        # 5: add them to the cart
        page.get_by_test_id("add-to-cart-sauce-labs-onesie").click()
        page.get_by_test_id("add-to-cart-sauce-labs-bike-light").click()
        _check(page.get_by_test_id("shopping-cart-badge").inner_text() == "2", "cart badge != 2")

        # 6: cart -> checkout -> made-up details
        page.get_by_test_id("shopping-cart-link").click()
        page.get_by_test_id("checkout").click()
        page.get_by_test_id("firstName").fill("Priya")
        page.get_by_test_id("lastName").fill("Demo")
        page.get_by_test_id("postalCode").fill("94103")
        page.get_by_test_id("continue").click()
        page.wait_for_url("**/checkout-step-two.html")

        # 7: order total on the overview page
        raw = page.get_by_test_id("total-label").inner_text()
        m = re.search(r"\$\d+\.\d\d", raw)
        _check(m, f"no dollar total in {raw!r}")
        total = m.group()

        # 8: finish + confirmation
        page.get_by_test_id("finish").click()
        _check("thank you" in page.get_by_test_id("complete-header").inner_text().lower(),
               "no thank-you header after finish")

        # session state AFTER checkout = logged in with an empty cart
        page.context.storage_state(path=str(STATE))
        browser.close()

    steps = [
        {"n": 1, "title": "Log in",
         "action": "browser_goto https://www.saucedemo.com, browser_fill test id `username` with "
                   "standard_user, browser_fill test id `password` with secret_sauce, then "
                   "browser_click test id `login-button`.",
         "locator": "test id `username`, test id `password`, test id `login-button`",
         "check": "browser_url ends with /inventory.html",
         "on_fail": "browser_goto https://www.saucedemo.com once more and retry the login; if the "
                    "URL still is not /inventory.html, report FAILED: step 1."},
        {"n": 2, "title": "Confirm the inventory page",
         "action": "browser_read_text test id `title`.",
         "locator": "test id `title`",
         "check": "The text is exactly `Products`.",
         "on_fail": "Retry browser_read_text once; if it is still not `Products`, report FAILED: step 2."},
        {"n": 3, "title": "Sort by price (low to high)",
         "action": "browser_select on the product sort dropdown, choosing exactly the option named "
                   "in the Locator below.",
         "locator": "test id `product-sort-container` - option `lohi` (Price: low to high)",
         "check": "browser_all_texts on test id `inventory-item-price` returns prices in ascending "
                  "order, and the first two are `$7.99` and `$9.99`.",
         "on_fail": "Re-select the option and re-read the prices once; if they are still not ascending, "
                    "report FAILED: step 3."},
        {"n": 4, "title": "Identify the two cheapest items",
         "action": "browser_all_texts on test id `inventory-item-name`.",
         "locator": "test id `inventory-item-name`",
         "check": "The first two names are `Sauce Labs Onesie` and `Sauce Labs Bike Light`.",
         "on_fail": "Report FAILED: step 4 - unexpected item order."},
        {"n": 5, "title": "Add the two cheapest items to the cart",
         "action": "browser_click test id `add-to-cart-sauce-labs-onesie`, then browser_click test id "
                   "`add-to-cart-sauce-labs-bike-light`.",
         "locator": "test id `add-to-cart-sauce-labs-onesie`, test id `add-to-cart-sauce-labs-bike-light`",
         "check": "browser_read_text on test id `shopping-cart-badge` returns `2`.",
         "on_fail": "Re-click whichever add button had no effect, re-read the badge once; if it is still "
                    "not `2`, report FAILED: step 5."},
        {"n": 6, "title": "Cart, checkout, made-up details",
         "action": "browser_click test id `shopping-cart-link`, then browser_click test id `checkout`. "
                   "browser_fill test id `firstName` with `Priya`, test id `lastName` with `Demo`, "
                   "test id `postalCode` with `94103`, then browser_click test id `continue`.",
         "locator": "test id `shopping-cart-link`, test id `checkout`, test id `firstName`, "
                    "test id `lastName`, test id `postalCode`, test id `continue`",
         "check": "browser_url ends with /checkout-step-two.html",
         "on_fail": "Re-fill any field the page complained about and click `continue` once more; if the "
                    "URL still is not /checkout-step-two.html, report FAILED: step 6."},
        {"n": 7, "title": "Read the order total",
         "action": "browser_read_text test id `total-label`.",
         "locator": "test id `total-label`",
         "check": "The text contains `Total: $` followed by an amount, e.g. `Total: $19.42`.",
         "on_fail": "Re-read once; if there is still no dollar amount, report FAILED: step 7."},
        {"n": 8, "title": "Finish and confirm",
         "action": "browser_click test id `finish`, then browser_read_text test id `complete-header`.",
         "locator": "test id `finish`, test id `complete-header`",
         "check": "The header contains `Thank you for your order`.",
         "on_fail": "Re-read once; if the header is still missing, report FAILED: step 8."},
    ]
    STEPS.parent.mkdir(exist_ok=True)
    STEPS.write_text(json.dumps({"steps": steps}, indent=2))
    return {"total": total, "steps_recorded": len(steps), "state": str(STATE)}


if __name__ == "__main__":
    r = record()
    print(f"recorded {r['steps_recorded']} steps -> {STEPS}")
    print(f"session -> {r['state']}")
    print("recorded total:", r["total"])
