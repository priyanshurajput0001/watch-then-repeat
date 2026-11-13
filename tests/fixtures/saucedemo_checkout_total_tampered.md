# Skill: Saucedemo checkout

## Goal
Replay the recorded workflow and return the **order total**.

## Preconditions
- Start URL: `https://www.saucedemo.com/`
- Saved session: `artifacts/state.json` (storage state captured right after login, before any cart changes).
- If the session is valid, open the site with it and **skip steps 1-3** (login).
- A **fresh login is needed** when: the state file is missing, or opening a protected page redirects to the login page, or the login form is visible. Then run steps 1-3 and re-save the session.
- Cart must be empty before step 4. Only ever allow navigation within the start URL's domain.

## Steps
Use auto-waiting actions only; no fixed sleeps. Try locators in the listed order.

1. Fill **Username** with `standard_user` _(intent: Log in with the demo user shown on the login page)_
   - Locator: `page.get_by_test_id("username")`
   - Fallback: `page.get_by_role("textbox", name="Username", exact=True)`
   - Fallback: `page.get_by_label("Username", exact=True)`
   - Fallback: `page.get_by_placeholder("Username", exact=True)`
   - Fallback: `page.locator("#user-name")`
   - Check: field holds `standard_user`

2. Fill **Password** with `secret_sauce` _(intent: Log in with the demo user shown on the login page)_
   - Locator: `page.get_by_test_id("password")`
   - Fallback: `page.get_by_role("textbox", name="Password", exact=True)`
   - Fallback: `page.get_by_label("Password", exact=True)`
   - Fallback: `page.get_by_placeholder("Password", exact=True)`
   - Fallback: `page.locator("#password")`
   - Check: field holds `secret_sauce`

3. Click **Login** _(intent: Log in with the demo user shown on the login page)_
   - Locator: `page.get_by_test_id("login-button")`
   - Fallback: `page.get_by_role("button", name="Login", exact=True)`
   - Fallback: `page.locator("#login-button")`
   - Check: URL path is `/inventory.html`
   - Check: `[data-test="header-container"]` shows "Open Menu All Items Dynamic Catalog About Logout Reset App State Close Menu Swag"
   - Check: `[data-test="primary-header"]` shows "Open Menu All Items Dynamic Catalog About Logout Reset App State Close Menu Swag"
   - Check: `[data-test="inventory-sidebar-link"]` shows "All Items"
   - Check: `[data-test="dynamic-catalog-sidebar-link"]` shows "Dynamic Catalog"

4. Select "Price (low to high)" (value `lohi`) in **Sort products** _(intent: Sort products by price, low to high)_
   - Locator: `page.get_by_test_id("product-sort-container")`
   - Fallback: `page.get_by_role("combobox", name="Sort products", exact=True)`
   - Fallback: `page.get_by_label("Sort products", exact=True)`
   - Check: `[data-test="secondary-header"]` shows "Products Price (low to high) Name (A to Z) Name (Z to A) Price (low to high) Pri"
   - Check: `[data-test="active-option"]` shows "Price (low to high)"
   - Check: `[data-test="inventory-container"]` shows "Sauce Labs Onesie Rib snap infant onesie for the junior automation engineer in d"
   - Check: `[data-test="inventory-list"]` shows "Sauce Labs Onesie Rib snap infant onesie for the junior automation engineer in d"
   - Check: `[data-test="inventory-item"]` shows "Sauce Labs Onesie Rib snap infant onesie for the junior automation engineer in d"

5. Click **Add to cart** _(intent: Add the two cheapest items (first two after sorting))_
   - Locator: `page.get_by_test_id("add-to-cart-sauce-labs-onesie")`
   - Fallback: `page.get_by_role("button", name="Add to cart", exact=True)`
   - Fallback: `page.get_by_text("Add to cart", exact=True)`
   - Fallback: `page.locator("#add-to-cart-sauce-labs-onesie")`
   - Check: `[data-test="shopping-cart-link"]` shows "1"
   - Check: `[data-test="shopping-cart-badge"]` shows "1"

6. Click **Add to cart** _(intent: Add the two cheapest items (first two after sorting))_
   - Locator: `page.get_by_test_id("add-to-cart-sauce-labs-bike-light")`
   - Fallback: `page.get_by_role("button", name="Add to cart", exact=True)`
   - Fallback: `page.get_by_text("Add to cart", exact=True)`
   - Fallback: `page.locator("#add-to-cart-sauce-labs-bike-light")`
   - Check: `[data-test="shopping-cart-link"]` shows "2"
   - Check: `[data-test="shopping-cart-badge"]` shows "2"

7. Click **Cart, 2 items** _(intent: Open the cart and start checkout)_
   - Locator: `page.get_by_test_id("shopping-cart-link")`
   - Fallback: `page.get_by_role("button", name="Cart, 2 items", exact=True)`
   - Fallback: `page.get_by_label("Cart, 2 items", exact=True)`
   - Fallback: `page.get_by_text("2", exact=True)`
   - Check: URL path is `/cart.html`
   - Check: `[data-test="header-container"]` shows "Open Menu Swag Labs 2 Your Cart"
   - Check: `[data-test="primary-header"]` shows "Open Menu Swag Labs 2"
   - Check: `[data-test="secondary-header"]` shows "Your Cart"
   - Check: `[data-test="title"]` shows "Your Cart"

8. Click **Checkout** _(intent: Open the cart and start checkout)_
   - Locator: `page.get_by_test_id("checkout")`
   - Fallback: `page.get_by_role("button", name="Checkout", exact=True)`
   - Fallback: `page.get_by_text("Checkout", exact=True)`
   - Fallback: `page.locator("#checkout")`
   - Check: URL path is `/checkout-step-one.html`
   - Check: `[data-test="header-container"]` shows "Open Menu Swag Labs 2 Checkout: Your Information"
   - Check: `[data-test="secondary-header"]` shows "Checkout: Your Information"
   - Check: `[data-test="title"]` shows "Checkout: Your Information"
   - Check: `[data-test="checkout-info-container"]` shows "Cancel"

9. Fill **First Name** with `Test` _(intent: Enter made-up checkout details)_
   - Locator: `page.get_by_test_id("firstName")`
   - Fallback: `page.get_by_role("textbox", name="First Name", exact=True)`
   - Fallback: `page.get_by_label("First Name", exact=True)`
   - Fallback: `page.get_by_placeholder("First Name", exact=True)`
   - Fallback: `page.locator("#first-name")`
   - Check: field holds `Test`

10. Fill **Last Name** with `User` _(intent: Enter made-up checkout details)_
   - Locator: `page.get_by_test_id("lastName")`
   - Fallback: `page.get_by_role("textbox", name="Last Name", exact=True)`
   - Fallback: `page.get_by_label("Last Name", exact=True)`
   - Fallback: `page.get_by_placeholder("Last Name", exact=True)`
   - Fallback: `page.locator("#last-name")`
   - Check: field holds `User`

11. Fill **Zip/Postal Code** with `12345` _(intent: Enter made-up checkout details)_
   - Locator: `page.get_by_test_id("postalCode")`
   - Fallback: `page.get_by_role("textbox", name="Zip/Postal Code", exact=True)`
   - Fallback: `page.get_by_label("Zip/Postal Code", exact=True)`
   - Fallback: `page.get_by_placeholder("Zip/Postal Code", exact=True)`
   - Fallback: `page.locator("#postal-code")`
   - Check: field holds `12345`

12. Click **Continue** _(intent: Enter made-up checkout details)_
   - Locator: `page.get_by_test_id("continue")`
   - Fallback: `page.get_by_role("button", name="Continue", exact=True)`
   - Fallback: `page.locator("#continue")`
   - Check: URL path is `/checkout-step-two.html`
   - Check: `[data-test="header-container"]` shows "Open Menu Swag Labs 2 Checkout: Overview"
   - Check: `[data-test="secondary-header"]` shows "Checkout: Overview"
   - Check: `[data-test="title"]` shows "Checkout: Overview"
   - Check: `[data-test="checkout-summary-container"]` shows "QTYDescription 1 Sauce Labs Onesie Rib snap infant onesie for the junior automat"

13. Read **order total** with `inner_text()` and keep it as the result: `Total: $88.88` _(intent: Read the order total on the overview page)_
   - Locator: `page.get_by_test_id("total-label")`
   - Fallback: `page.get_by_text("Total: $88.88", exact=True)`
   - Check: value is non-empty

14. Click **Finish** _(intent: Finish the order and confirm the thank-you page)_
   - Locator: `page.get_by_test_id("finish")`
   - Fallback: `page.get_by_role("button", name="Finish", exact=True)`
   - Fallback: `page.get_by_text("Finish", exact=True)`
   - Fallback: `page.locator("#finish")`
   - Check: URL path is `/checkout-complete.html`
   - Check: `[data-test="header-container"]` shows "Open Menu Swag Labs Checkout: Complete!"
   - Check: `[data-test="primary-header"]` shows "Open Menu Swag Labs"
   - Check: `[data-test="secondary-header"]` shows "Checkout: Complete!"
   - Check: `[data-test="title"]` shows "Checkout: Complete!"

## When a check fails
1. Re-run the step's locator fallbacks once, then wait for the check condition (auto-wait, max ~10s).
2. If the URL is the login page, the session expired: do a fresh login, re-save the session, restart from the first non-login step.
3. If a check still fails, **stop**. Do not improvise or skip ahead. Report the step number, the expected check and what the page actually shows.
4. Never navigate outside the allowed domain.
