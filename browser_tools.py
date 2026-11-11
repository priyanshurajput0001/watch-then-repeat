"""The replay agent's ONLY browser tools. Async Playwright, auto-waiting, request logging."""
import json
import os
import time
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool
from playwright.async_api import async_playwright

LOGS = Path("logs")
_S: dict = {}


def _ok(text):
    return {"content": [{"type": "text", "text": str(text)}]}


async def _route(route):
    page = _S.get("page")
    url = page.url if page else ""
    if "/checkout-" in url:  # network interception: log every request made at checkout
        LOGS.mkdir(exist_ok=True)
        r = route.request
        with open(LOGS / "network.jsonl", "a") as f:
            f.write(json.dumps({"t": time.time(), "page": url, "method": r.method,
                                "type": r.resource_type, "url": r.url}) + "\n")
    await route.continue_()


async def _start(storage=None):
    await close_browser()
    pw = await async_playwright().start()
    pw.selectors.set_test_id_attribute("data-test")
    browser = await pw.chromium.launch(headless=os.getenv("HEADED") != "1")
    ctx = await browser.new_context(storage_state=storage)
    page = await ctx.new_page()
    page.set_default_timeout(10_000)
    await ctx.route("**/*", _route)
    _S.update(pw=pw, browser=browser, ctx=ctx, page=page)


async def _page():
    if "page" not in _S:
        await _start()
    return _S["page"]


async def close_browser():
    if "browser" in _S:
        await _S["browser"].close()
        await _S["pw"].stop()
    _S.clear()


def _loc(page, kind, value, name="", nth=0):
    if kind == "test_id":
        l = page.get_by_test_id(value)
    elif kind == "role":
        l = page.get_by_role(value, name=name or None)
    elif kind == "label":
        l = page.get_by_label(value)
    elif kind == "text":
        l = page.get_by_text(value)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return l.nth(int(nth))


LOC = {"kind": str, "value": str, "name": str, "nth": int}


@tool("browser_load_session", "Start a browser from the saved logged-in session (artifacts/state.json).", {})
async def browser_load_session(args):
    p = Path("artifacts/state.json")
    if not p.exists():
        return _ok("NO_SESSION: artifacts/state.json not found. Do a fresh login.")
    await _start(storage=str(p))
    return _ok("session loaded")


@tool("browser_goto", "Navigate to a URL.", {"url": str})
async def browser_goto(args):
    page = await _page()
    await page.goto(args["url"])
    return _ok(f"at {page.url}")


@tool("browser_click", "Click an element (auto-waits).", LOC)
async def browser_click(args):
    page = await _page()
    await _loc(page, args["kind"], args["value"], args["name"], args["nth"]).click()
    return _ok(f"clicked; url={page.url}")


@tool("browser_fill", "Fill a text field (auto-waits).", {**LOC, "text": str})
async def browser_fill(args):
    page = await _page()
    await _loc(page, args["kind"], args["value"], args["name"], args["nth"]).fill(args["text"])
    return _ok("filled")


@tool("browser_select", "Select a <select> option by its value.", {"kind": str, "value": str, "option": str})
async def browser_select(args):
    page = await _page()
    await _loc(page, args["kind"], args["value"]).select_option(args["option"])
    return _ok("selected")


@tool("browser_read_text", "Read an element's text (waits until visible).", LOC)
async def browser_read_text(args):
    page = await _page()
    l = _loc(page, args["kind"], args["value"], args["name"], args["nth"])
    await l.wait_for(state="visible")
    return _ok(await l.inner_text())


@tool("browser_all_texts", "Read the text of ALL matching elements, as a JSON list.",
      {"kind": str, "value": str, "name": str})
async def browser_all_texts(args):
    page = await _page()
    l = _loc(page, args["kind"], args["value"], args["name"], 0)
    await l.first.wait_for(state="visible")
    base = l.page.get_by_test_id(args["value"]) if args["kind"] == "test_id" else None
    texts = await (base or l).all_inner_texts()
    return _ok(json.dumps(texts))


@tool("browser_url", "Return the current page URL.", {})
async def browser_url(args):
    return _ok((await _page()).url)


_TOOLS = [browser_load_session, browser_goto, browser_click, browser_fill, browser_select,
          browser_read_text, browser_all_texts, browser_url]
browser_server = create_sdk_mcp_server(name="browser", version="1.0.0", tools=_TOOLS)
TOOL_NAMES = [f"mcp__browser__{t.name}" for t in _TOOLS]
