# Skill: Buy the two cheapest items on saucedemo.com

## Goal
Log in with the demo user, sort by price (low to high), add the two cheapest items, check out with made-up details, read the order total from the overview page, finish, and confirm the thank-you page. Return the order total.

## Preconditions
- Only https://www.saucedemo.com is allowed. Never navigate anywhere else.
- Demo credentials only (shown on the login page). No real accounts.
- The cart must be empty at the start. A fresh browser session guarantees that.

## Session
- The recorder saved a logged-in session to `artifacts/state.json`.
- To start from it, call `browser_load_session`, then `browser_goto` to `https://www.saucedemo.com/inventory.html`, then continue at step 3.
- **A fresh login is needed** (do steps 1-2) if there is no saved session, or if `/inventory.html` redirects to the login page.
- If you start without a saved session, begin at step 1.

## Tool guide
- `kind` is one of `test_id`, `role`, `label`, `text`. For `role`, put the role in `value` and the accessible name in `name`. Pass `name=""` and `nth=0` when unused.
- A locator like "test id `login-button`" means `kind=test_id, value=login-button`.
- Tools wait for elements automatically. Never guess a CSS path.
- Check URLs with `browser_url`, text with `browser_read_text`, lists with `browser_all_texts`.

## Steps
### Step 1: Log in
- **Do:** browser_goto https://www.saucedemo.com, browser_fill test id `username` with standard_user, browser_fill test id `password` with secret_sauce, then browser_click test id `login-button`.
- **Locator:** test id `username`, test id `password`, test id `login-button`
- **Check:** browser_url ends with /inventory.html
- **If the check fails:** browser_goto https://www.saucedemo.com once more and retry the login; if the URL still is not /inventory.html, report FAILED: step 1.

### Step 2: Confirm the inventory page
- **Do:** browser_read_text test id `title`.
- **Locator:** test id `title`
- **Check:** The text is exactly `Products`.
- **If the check fails:** Retry browser_read_text once; if it is still not `Products`, report FAILED: step 2.

### Step 3: Sort by price (low to high)
- **Do:** browser_select on the product sort dropdown, choosing exactly the option named in the Locator below.
- **Locator:** test id `product-sort-container` - option `lohi` (Price: low to high)
- **Check:** browser_all_texts on test id `inventory-item-price` returns prices in ascending order, and the first two are `$7.99` and `$9.99`.
- **If the check fails:** Re-select the option and re-read the prices once; if they are still not ascending, report FAILED: step 3.

### Step 4: Identify the two cheapest items
- **Do:** browser_all_texts on test id `inventory-item-name`.
- **Locator:** test id `inventory-item-name`
- **Check:** The first two names are `Sauce Labs Onesie` and `Sauce Labs Bike Light`.
- **If the check fails:** Report FAILED: step 4 - unexpected item order.

### Step 5: Add the two cheapest items to the cart
- **Do:** browser_click test id `add-to-cart-sauce-labs-onesie`, then browser_click test id `add-to-cart-sauce-labs-bike-light`.
- **Locator:** test id `add-to-cart-sauce-labs-onesie`, test id `add-to-cart-sauce-labs-bike-light`
- **Check:** browser_read_text on test id `shopping-cart-badge` returns `2`.
- **If the check fails:** Re-click whichever add button had no effect, re-read the badge once; if it is still not `2`, report FAILED: step 5.

### Step 6: Cart, checkout, made-up details
- **Do:** browser_click test id `shopping-cart-link`, then browser_click test id `checkout`. browser_fill test id `firstName` with `Priya`, test id `lastName` with `Demo`, test id `postalCode` with `94103`, then browser_click test id `continue`.
- **Locator:** test id `shopping-cart-link`, test id `checkout`, test id `firstName`, test id `lastName`, test id `postalCode`, test id `continue`
- **Check:** browser_url ends with /checkout-step-two.html
- **If the check fails:** Re-fill any field the page complained about and click `continue` once more; if the URL still is not /checkout-step-two.html, report FAILED: step 6.

### Step 7: Read the order total
- **Do:** browser_read_text test id `total-label`.
- **Locator:** test id `total-label`
- **Check:** The text contains `Total: $` followed by an amount, e.g. `Total: $19.42`.
- **If the check fails:** Re-read once; if there is still no dollar amount, report FAILED: step 7.

### Step 8: Finish and confirm
- **Do:** browser_click test id `finish`, then browser_read_text test id `complete-header`.
- **Locator:** test id `finish`, test id `complete-header`
- **Check:** The header contains `Thank you for your order`.
- **If the check fails:** Re-read once; if the header is still missing, report FAILED: step 8.

## If any step fails
Stop. Reply exactly `FAILED: step N - <what you saw>`. Do not continue and do not guess.

## Output
Reply with exactly one final line: `ORDER_TOTAL: $xx.xx` (the total from step 7).
