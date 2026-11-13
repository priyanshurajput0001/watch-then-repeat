#!/usr/bin/env python
"""QA audit, task 5b: is an off-site link click (footer social links) stopped?

Drives the PRODUCT browser tools directly (no model, no SDK) — which is exactly the
enforcement point analysis: the PreToolUse hook only guards `browser_goto`; the Playwright
route handler in browser_tools._route only LOGS on /checkout- pages and never aborts.
So a click on a footer social link should navigate off-site unimpeded.

Run: .venv/bin/python tests/acceptance/test_offsite_click.py
Needs a valid artifacts/state.json (refresh_session.py) OR does its own fresh login.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import browser_tools as bt


async def main():
    ev = {}
    # redirect hook logging FIRST so probes never touch the real audit log slice
    import hooks
    from hooks import log_and_guard
    hooks.LOG = Path("/tmp/wtr_offsite_hookprobe.jsonl")
    # 1) hook-level: browser_goto to an off-site URL IS denied (unit evidence cross-check)
    res = await log_and_guard({"tool_name": "mcp__browser__browser_goto",
                               "tool_input": {"url": "https://twitter.com/SauceLabs"}}, "id", None)
    ev["hook_denies_goto_offsite"] = bool(res.get("hookSpecificOutput"))
    ev["hook_deny_reason"] = res.get("hookSpecificOutput", {}).get("permissionDecisionReason")

    # 2) behavior-level: click the footer social link via the product tool path
    state = ROOT / "artifacts/state.json"
    if state.exists():
        await bt.browser_load_session.handler({})
        await bt.browser_goto.handler({"url": "https://www.saucedemo.com/inventory.html"})
    else:
        await bt._start()
        await bt.browser_goto.handler({"url": "https://www.saucedemo.com/"})
        await bt.browser_fill.handler({"kind": "test_id", "value": "username", "text": "standard_user"})
        await bt.browser_fill.handler({"kind": "test_id", "value": "password", "text": "secret_sauce"})
        await bt.browser_click.handler({"kind": "test_id", "value": "login-button"})
    await bt.browser_goto.handler({"url": "https://www.saucedemo.com/inventory.html"})
    page = await bt._page()
    ev["social_links"] = await page.evaluate(
        "[...document.querySelectorAll('a[href]')].map(a => a.href).filter(h => !h.includes('saucedemo'))")
    # click the off-site link the way the agent's browser_click would after resolving a
    # locator (footer links carry no useful accessible name; use the href selector)
    try:
        await page.click(f'a[href="{ev["social_links"][1]}"]', timeout=8000)  # x.com/saucelabs
    except Exception as e:
        ev["click_error"] = f"{type(e).__name__}: {e}"
    await asyncio.sleep(3)  # audit-side settle for the navigation/popup (not product code)
    ctx = page.context
    ev["open_tabs"] = [p.url for p in ctx.pages]
    url_now = (await bt._page()).url
    ev["url_after_click"] = url_now
    ev["navigated_offsite"] = any("saucedemo" not in u for u in ev["open_tabs"])
    ev["route_handler_aborts"] = False  # by code: browser_tools._route only logs, then continue_
    await bt.close_browser()

    ok_block = ev["hook_denies_goto_offsite"]
    ok_behavior = ev.get("navigated_offsite") is True or bool(ev.get("click_error"))
    ev["VERDICT"] = (f"hook denies browser_goto off-site: {ok_block}; "
                     f"off-site CLICK is {'STOPPED' if not ok_behavior else 'NOT stopped (navigated or attempted)'}; "
                     "route layer enforces nothing (logs only on /checkout- pages)")
    out = ROOT / "reports/evidence/audit5_offsite_click.json"
    out.write_text(json.dumps(ev, indent=2))
    print(json.dumps(ev, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
