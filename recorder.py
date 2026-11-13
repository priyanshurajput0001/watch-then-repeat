"""recorder.py - turn a Playwright run into OBSERVED steps and a skill file.

Sync Playwright API. Usage:

    pw.selectors.set_test_id_attribute("data-test")   # saucedemo uses data-test
    ctx = browser.new_context()
    rec = Observer(ctx)            # BEFORE ctx.new_page()
    page = ctx.new_page()
    with rec.intent("Log in with the demo user"):
        ...drive the page...
    steps = rec.finish(page)       # list[dict], derived from observed events
    Path("skills/x.md").write_text(render_skill(steps, ...))
"""
import json
from contextlib import contextmanager
from pathlib import Path

# --------------------------------------------------------------------------
# Browser side: listens for real events, describes the element, snapshots state
# --------------------------------------------------------------------------
INIT_JS = r"""
(() => {
  if (window.__rec_installed) return;
  window.__rec_installed = true;
  const clean = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const IMPLICIT = {BUTTON: 'button', SELECT: 'combobox', TEXTAREA: 'textbox'};
  const TEXTLESS = ['checkbox', 'radio', 'button', 'submit', 'reset'];

  const role = el => {
    const r = el.getAttribute('role'); if (r) return r;
    if (el.tagName === 'INPUT') {
      const t = (el.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset'].includes(t)) return 'button';
      return {checkbox: 'checkbox', radio: 'radio'}[t] || 'textbox';
    }
    if (el.tagName === 'A' && el.hasAttribute('href')) return 'link';
    return IMPLICIT[el.tagName] || null;
  };
  const label = el => (el.labels && el.labels[0]) ? clean(el.labels[0].innerText)
                      : clean(el.getAttribute('aria-label'));
  const accName = el => clean(
    el.getAttribute('aria-label') ||
    (el.labels && el.labels[0] && el.labels[0].innerText) ||
    (el.tagName === 'INPUT' && ['button', 'submit', 'reset'].includes(el.type) ? el.value : '') ||
    el.innerText || el.getAttribute('title'));

  window.__describe = el => ({
    tag: el.tagName.toLowerCase(),
    testid: el.getAttribute('data-test'),
    role: role(el), name: accName(el), label: label(el),
    placeholder: el.getAttribute('placeholder'),
    text: clean(el.innerText), id: el.id || null,
  });

  // Visible short text of every [data-test] element (first one per key).
  window.__snapshot = () => {
    const texts = {};
    document.querySelectorAll('[data-test]').forEach(el => {
      if (['BUTTON', 'INPUT'].includes(el.tagName) || !el.getClientRects().length) return;
      const k = el.getAttribute('data-test'), t = clean(el.innerText);
      if (t && !(k in texts)) texts[k] = t;
    });
    return {url: location.pathname, texts};
  };

  const send = (action, el, value, shown) => {
    try {
      window.__rec({action, desc: window.__describe(el), value: value ?? null,
                    shown: shown ?? null, before: window.__snapshot()});
    } catch (_) {}
  };
  const target = e => e.target.closest(
    'button,a[href],input,select,textarea,[role=button],[data-test]') || e.target;

  // capture phase => runs BEFORE the app's handlers, so `before` is the pre-action DOM
  document.addEventListener('click', e => {
    const el = target(e);
    if (['SELECT', 'OPTION', 'TEXTAREA'].includes(el.tagName)) return;
    if (el.tagName === 'INPUT' && !TEXTLESS.includes(el.type)) return;  // focus click
    send('click', el);
  }, true);
  document.addEventListener('input', e => {
    const el = e.target;
    if (el.tagName === 'TEXTAREA' ||
        (el.tagName === 'INPUT' && !TEXTLESS.includes(el.type))) send('fill', el, el.value);
  }, true);
  document.addEventListener('change', e => {
    const el = e.target;
    if (el.tagName === 'SELECT')
      send('select', el, el.value, el.selectedOptions[0] && el.selectedOptions[0].text);
  }, true);
})();
"""


# --------------------------------------------------------------------------
# Locator priority: data-test > role+name > label > placeholder > text > css id
# --------------------------------------------------------------------------
def _q(s):
    return json.dumps(s)


def pick_locators(d):
    """Return Playwright locator expressions, most stable first."""
    out = []
    if d.get("testid"):
        out.append(f'get_by_test_id({_q(d["testid"])})')
    if d.get("role") and d.get("name"):
        out.append(f'get_by_role({_q(d["role"])}, name={_q(d["name"])}, exact=True)')
    if d.get("label"):
        out.append(f'get_by_label({_q(d["label"])}, exact=True)')
    if d.get("placeholder"):
        out.append(f'get_by_placeholder({_q(d["placeholder"])}, exact=True)')
    if d.get("text") and len(d["text"]) <= 40:
        out.append(f'get_by_text({_q(d["text"])}, exact=True)')
    if d.get("id"):
        out.append(f'locator({_q("#" + d["id"])})')  # last resort
    return out


# Site chrome (header bars, menus, sidebars) flips between runs — burger-menu open/close
# text, sidebar entries — so a chrome check can never pass reliably. Checks pin page content.
_CHROME = ("header", "menu", "sidebar")


def _is_chrome(testid):
    return any(w in testid for w in _CHROME)


def derive_checks(step):
    """Checks come from diffing observed before/after state, not hand-written.
    Chrome (header/menu/sidebar) is never checked; a navigation step whose text
    checks are all chrome anchors on the page's content list instead."""
    before, after = step["before"], step["after"]
    checks = []
    if step["action"] == "fill":
        checks.append({"type": "value", "value": step["value"]})
    if step["action"] == "read":
        return [{"type": "nonempty"}]
    if after["url"] != before["url"]:
        checks.append({"type": "url", "value": after["url"]})
    for k, v in after["texts"].items():
        if before["texts"].get(k) != v:
            checks.append({"type": "text", "testid": k, "value": v})
    checks = checks[:5]
    kept = [c for c in checks if not (c["type"] == "text" and _is_chrome(c["testid"]))]
    if any(c["type"] == "url" for c in kept) and not any(c["type"] == "text" for c in kept):
        anchor = next((k for k, v in after["texts"].items()
                       if before["texts"].get(k) != v and not _is_chrome(k)
                       and k.endswith("-list")), None)
        if anchor:
            kept.append({"type": "text", "testid": anchor, "value": after["texts"][anchor]})
    return kept


def _item_name(slug):
    """Full display name derived from an add-to-cart testid slug
    (sauce-labs-onesie -> Sauce Labs Onesie). Never passes through the snapshot's
    80-char cleaner, so it is untruncated by construction."""
    return " ".join(w.capitalize() for w in slug.split("-"))


def add_item_name_checks(steps):
    """Fix 4: badge counts and 80-char text blobs can't tell a swapped item apart, so
    every recorded add-to-cart item must appear by its FULL name on the cart and
    overview pages. Appended after derive_checks: exempt from the 5-check cap, the
    snapshot truncation and the _CHROME filter."""
    slugs = []
    for s in steps:
        tid = s["desc"].get("testid") or ""
        if s["action"] == "click" and tid.startswith("add-to-cart-") and tid not in slugs:
            slugs.append(tid[len("add-to-cart-"):])
    for s in steps:
        if s["action"] == "click" and s["before"]["url"] != s["after"]["url"] and (
                s["after"]["url"].endswith("/cart.html")
                or s["after"]["url"].endswith("/checkout-step-two.html")):
            s["checks"] += [{"type": "item_name", "value": _item_name(slug)} for slug in slugs]
    return steps


# --------------------------------------------------------------------------
# Python side
# --------------------------------------------------------------------------
class Observer:
    def __init__(self, context):
        self.raw = []
        self._intent = None
        context.expose_binding("__rec", self._on_event)  # must precede new_page()
        context.add_init_script(INIT_JS)

    @contextmanager
    def intent(self, text):
        """Label what the demonstrator is trying to do; attached to events inside."""
        self._intent = text
        try:
            yield
        finally:
            self._intent = None

    def _on_event(self, source, p):
        p["intent"] = self._intent
        last = self.raw[-1] if self.raw else None
        # coalesce keystrokes into one fill per field
        if (p["action"] == "fill" and last and last["action"] == "fill"
                and last["desc"] == p["desc"]):
            last["value"] = p["value"]
            return
        self.raw.append(p)

    def read(self, label, locator):
        """Record a read-a-value step (e.g. the order total)."""
        page = locator.page
        desc = locator.evaluate("el => window.__describe(el)")
        snap = page.evaluate("window.__snapshot()")
        self.raw.append({"action": "read", "desc": desc, "value": locator.inner_text().strip(),
                         "shown": label, "before": snap, "intent": self._intent})

    def finish(self, page):
        final = page.evaluate("window.__snapshot()")
        steps = []
        for i, e in enumerate(self.raw):
            if e["action"] == "read":
                after = e["before"]
            else:  # state after step i == state seen right before step i+1
                after = self.raw[i + 1]["before"] if i + 1 < len(self.raw) else final
            s = {**e, "n": i + 1, "after": after}
            s["locators"] = pick_locators(e["desc"])
            s["checks"] = derive_checks(s)
            steps.append(s)
        return add_item_name_checks(steps)


# --------------------------------------------------------------------------
# Skill renderer
# --------------------------------------------------------------------------
def _target(d):
    return d.get("name") or d.get("label") or d.get("placeholder") or d.get("testid") or d["tag"]


def _check_line(c):
    if c["type"] == "url":
        return f'URL path is `{c["value"]}`'
    if c["type"] == "text":
        return f'`[data-test="{c["testid"]}"]` shows "{c["value"]}"'
    if c["type"] == "value":
        return f'field holds `{c["value"]}`'
    if c["type"] == "item_name":
        return (f'the page shows the full item name "{c["value"]}" — search all element '
                'text; a truncated prefix does not satisfy this')
    return "value is non-empty"


def _step_line(s):
    t, v = _target(s["desc"]), s["value"]
    return {
        "click": f"Click **{t}**",
        "fill": f"Fill **{t}** with `{v}`",
        "select": f'Select "{s["shown"]}" (value `{v}`) in **{t}**',
        "read": f'Read **{s["shown"]}** with `inner_text()` and keep it as the result: `{v}`',
    }[s["action"]]


def render_skill(steps, start_url, state_path, title="Workflow", result_name="order total"):
    login_n = 0  # leading steps that happen on the start page => skipped if session valid
    for s in steps:
        if s["before"]["url"] == steps[0]["before"]["url"]:
            login_n += 1
        else:
            break
    L = [f"# Skill: {title}", "",
         "## Goal", f"Replay the recorded workflow and return the **{result_name}**.", "",
         "## Preconditions",
         f"- Start URL: `{start_url}`",
         f"- Saved session: `{state_path}` (storage state captured right after login, "
         "before any cart changes).",
         f"- If the session is valid, open the site with it and **skip steps 1-{login_n}** (login).",
         "- A **fresh login is needed** when: the state file is missing, or opening a protected "
         "page redirects to the login page, or the login form is visible. Then run steps "
         f"1-{login_n} and re-save the session.",
         "- Cart must be empty before step "
         f"{login_n + 1}. Only ever allow navigation within the start URL's domain.", "",
         "## Steps", "Use auto-waiting actions only; no fixed sleeps. Try locators in the listed order.", ""]
    for s in steps:
        L.append(f'{s["n"]}. {_step_line(s)}' + (f' _(intent: {s["intent"]})_' if s["intent"] else ""))
        for i, loc in enumerate(s["locators"]):
            L.append(f'   - {"Locator" if i == 0 else "Fallback"}: `page.{loc}`')
        for c in s["checks"]:
            L.append(f"   - Check: {_check_line(c)}")
        L.append("")
    L += ["## When a check fails",
          "1. Re-run the step's locator fallbacks once, then wait for the check condition (auto-wait, max ~10s).",
          "2. If the URL is the login page, the session expired: do a fresh login, re-save the session, "
          "restart from the first non-login step.",
          "3. If a check still fails, **stop**. Do not improvise or skip ahead. Report the step number, "
          "the expected check and what the page actually shows.",
          "4. Never navigate outside the allowed domain."]
    read_n = next((s["n"] for s in steps if s["action"] == "read"), None)
    amount = (f"the **{result_name}** read live from the page during step {read_n}'s Read "
              "(its `inner_text()`)" if read_n else f"the **{result_name}** read live from the page")
    L += ["## Output",
          "End your final reply with exactly one sentinel line, on a line of its own:",
          f"- Success: `ORDER_TOTAL: $X.XX`, where the amount is {amount} — never a value quoted "
          "from this skill. Keep the dollar sign and exactly two decimals.",
          "- Failure: `FAILED_STEP: <n>`, where `<n>` is the number of the step that still fails "
          "after the retry rule above.",
          "Never emit both lines, and never restate a sentinel line elsewhere in the reply."]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# Demo: scripted demonstrator for saucedemo (replaces your hardcoded step list)
# --------------------------------------------------------------------------
def demonstrate(page, ctx, rec, state_path):
    START = "https://www.saucedemo.com/"
    page.goto(START)
    with rec.intent("Log in with the demo user shown on the login page"):
        page.get_by_test_id("username").fill("standard_user")
        page.get_by_test_id("password").fill("secret_sauce")
        page.get_by_test_id("login-button").click()
        page.wait_for_url("**/inventory.html")
    ctx.storage_state(path=state_path)  # save NOW: later the cart lives in localStorage
    with rec.intent("Sort products by price, low to high"):
        page.get_by_test_id("product-sort-container").select_option("lohi")
    with rec.intent("Add the two cheapest items (first two after sorting)"):
        items = page.get_by_test_id("inventory-item")
        for i in range(2):
            items.nth(i).get_by_role("button", name="Add to cart").click()
    with rec.intent("Open the cart and start checkout"):
        page.get_by_test_id("shopping-cart-link").click()
        page.get_by_test_id("checkout").click()
    with rec.intent("Enter made-up checkout details"):
        page.get_by_test_id("firstName").fill("Test")
        page.get_by_test_id("lastName").fill("User")
        page.get_by_test_id("postalCode").fill("12345")
        page.get_by_test_id("continue").click()
    with rec.intent("Read the order total on the overview page"):
        rec.read("order total", page.get_by_test_id("total-label"))
    with rec.intent("Finish the order and confirm the thank-you page"):
        page.get_by_test_id("finish").click()
        page.get_by_test_id("complete-header").wait_for()
    return START


REC_DIR = Path("recordings/saucedemo_checkout")
STATE = "artifacts/state.json"
SKILL = Path("skills/saucedemo_checkout.md")


def record(state_path: str = STATE) -> dict:
    """One scripted demonstrator run, OBSERVED. Writes recordings/, the skill, and saves
    the storage state right after login (before any cart change)."""
    from playwright.sync_api import sync_playwright

    REC_DIR.mkdir(parents=True, exist_ok=True)
    Path(state_path).parent.mkdir(exist_ok=True)
    SKILL.parent.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        ctx.tracing.start(screenshots=True, snapshots=True)
        rec = Observer(ctx)
        page = ctx.new_page()
        start = demonstrate(page, ctx, rec, state_path)
        steps = rec.finish(page)
        ctx.tracing.stop(path=str(REC_DIR / "trace.zip"))
        browser.close()

    (REC_DIR / "steps.json").write_text(json.dumps(steps, indent=2))
    SKILL.write_text(render_skill(steps, start, state_path, title="Saucedemo checkout"))
    totals = [s["value"] for s in steps if s["action"] == "read"]
    return {"steps": len(steps), "total": totals[-1] if totals else None,
            "skill": str(SKILL), "recording": str(REC_DIR), "state": state_path}


if __name__ == "__main__":
    r = record()
    print(f"wrote {r['recording']}/ ({r['steps']} steps, total {r['total']}) and {r['skill']}")