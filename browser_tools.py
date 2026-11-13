"""The replay agent's ONLY browser tools. Async Playwright, auto-waiting, request logging."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from claude_agent_sdk import create_sdk_mcp_server, tool
from playwright.async_api import async_playwright

LOGS = Path("logs")
_S: dict = {}


def _ok(text):
    return {"content": [{"type": "text", "text": str(text)}]}


# Context-level allowlist (the hook only guards browser_goto; this guards the wire).
_ALLOWED_HOSTS = {"saucedemo.com", "www.saucedemo.com"}


def is_allowed_url(url: str) -> bool:
    """Only saucedemo.com / www.saucedemo.com over http(s), plus non-network schemes."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme in ("http", "https"):
        return u.hostname in _ALLOWED_HOSTS
    if u.scheme == "about":
        return url.startswith("about:blank")
    return u.scheme in ("data", "blob")


def _log_block(kind, url):
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "network.jsonl", "a") as f:
        f.write(json.dumps({"t": time.time(), "blocked": True, "kind": kind, "url": url}) + "\n")
    print(f"BLOCKED off-site {kind}: {url}", file=sys.stderr)


async def _route(route):
    url = route.request.url
    if not is_allowed_url(url):  # context-level wall: abort before it reaches the wire
        _log_block("request", url)
        return await route.abort()
    page = _S.get("page")
    purl = page.url if page else ""
    if "/checkout-" in purl:  # network interception: log every request made at checkout
        LOGS.mkdir(exist_ok=True)
        r = route.request
        with open(LOGS / "network.jsonl", "a") as f:
            f.write(json.dumps({"t": time.time(), "page": purl, "method": r.method,
                                "type": r.resource_type, "url": url}) + "\n")
    await route.continue_()


def _guard_popup(popup):
    """A new tab/popup must never end up off-site: close it, leaving the saucedemo
    page (always _S['page']) as the context's active page. Never guards that page."""
    if popup is _S.get("page"):  # the original page: route.abort already guards it
        return

    async def _close_if_offsite(url, why):
        if not is_allowed_url(url):
            _log_block(why, url)
            try:
                await popup.close()
            except Exception:
                pass
    popup.on("framenavigated",
             lambda f: f is popup.main_frame and asyncio.ensure_future(
                 _close_if_offsite(f.url, "tab")))
    # the first navigation can settle BEFORE the page event reaches us (an aborted
    # popup lands on chrome-error://); judge whatever it is right now
    asyncio.ensure_future(_close_if_offsite(popup.url, "tab"))


async def _start(storage=None):
    await close_browser()
    pw = await async_playwright().start()
    pw.selectors.set_test_id_attribute("data-test")
    browser = await pw.chromium.launch(headless=os.getenv("HEADED") != "1")
    ctx = await browser.new_context(storage_state=storage)
    page = await ctx.new_page()
    page.set_default_timeout(10_000)
    await ctx.route("**/*", _route)
    ctx.on("page", _guard_popup)  # pages opened AFTER the main one: off-site popups die
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
