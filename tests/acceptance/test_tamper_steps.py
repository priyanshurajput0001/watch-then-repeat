#!/usr/bin/env python
"""QA audit, task 10: STEP-LEVEL tamper harness (no model).

Executes a skill file verbatim against the live site: parses each step's Do line into an
action, resolves its Locator (then Fallbacks), performs it, then evaluates every Check line.
Reports the first failing step. This measures whether the SKILL'S OWN CHECKS catch a tamper
- the same mechanism the agent uses (proven at agent level by the repo-tamper replay R5).

Variants:
  pristine   skills/saucedemo_checkout.md
  a_step6    tests/fixtures/saucedemo_checkout_item_tampered_a.md (wrong item, 2nd add-to-cart)
  a_step5    in-memory: step 5 add-to-cart onesie -> bolt-t-shirt (wrong item, 1st add-to-cart)
  b          tests/fixtures/saucedemo_checkout_sort_tampered_b.md (wrong sort option, Do line)

Run: .venv/bin/python tests/acceptance/test_tamper_steps.py <variant>
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]


def parse_skill(text):
    m = re.search(r"^## Steps\b(.*?)^## When a check fails", text, re.M | re.S)
    body = m.group(1)
    blocks = re.split(r"(?=^\d+\. )", body, flags=re.M)
    steps = []
    for b in blocks:
        dm = re.match(r"^(\d+)\. (.*)", b)
        if not dm:
            continue
        n, do = int(dm.group(1)), dm.group(2)
        locs = re.findall(r"^   - (?:Locator|Fallback): `page\.(get_by_test_id|get_by_role|get_by_label"
                          r"|get_by_placeholder|get_by_text|locator)\((.*)\)`$", b, re.M)
        checks = re.findall(r"^   - Check: (.*)$", b, re.M)
        steps.append({"n": n, "do": do, "locs": locs, "checks": checks})
    return steps


def resolve(page, kind, args):
    s = re.search(r'"([^"]*)"', args)
    val = s.group(1) if s else ""
    nm = re.search(r'name=("",|"([^"]*)")', args)
    name = (nm.group(2) or "") if nm else ""
    if kind == "get_by_test_id":
        return page.get_by_test_id(val)
    if kind == "get_by_role":
        return page.get_by_role(val, name=name or None, exact=True)
    if kind == "get_by_label":
        return page.get_by_label(val, exact=True)
    if kind == "get_by_placeholder":
        return page.get_by_placeholder(val, exact=True)
    if kind == "get_by_text":
        return page.get_by_text(val, exact=True)
    return page.locator(val)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


async def eval_check(page, c, fieldval):
    m = re.match(r"URL path is `([^`]+)`", c)
    if m:
        return urlparse(page.url).path == m.group(1), f"url={urlparse(page.url).path} want {m.group(1)}"
    m = re.match(r'`\[data-test="([^"]+)"\]` shows "(.*)"$', c)
    if m:
        loc = page.get_by_test_id(m.group(1)).first
        got = ""
        for _ in range(3):  # skill's retry rule: wait for the check condition (auto-wait)
            try:
                await loc.wait_for(state="visible", timeout=8000)
                got = norm(await loc.inner_text())
            except Exception:
                return False, f"[data-test={m.group(1)}] not visible"
            if got.startswith(m.group(2)):
                return True, "ok"
            await asyncio.sleep(1.5)
        return False, f"got {got[:80]!r} want prefix {m.group(2)[:80]!r}"
    m = re.match(r"field holds `([^`]+)`", c)
    if m:
        return fieldval == m.group(1), f"field={fieldval!r}"
    if "non-empty" in c:
        return bool(fieldval and fieldval.strip()), f"value={fieldval!r}"
    return False, f"unparsed check {c!r}"


async def run_skill(pw, text, label):
    steps = parse_skill(text)
    browser = await pw.chromium.launch()
    ctx = await browser.new_context()
    page = await ctx.new_page()
    page.set_default_timeout(8000)
    result = {"label": label, "steps": [], "first_fail": None, "returned_total": None}
    fieldval = None
    try:
        await page.goto("https://www.saucedemo.com/")
        for s in steps:
            entry = {"n": s["n"], "do": s["do"][:60], "status": None, "detail": ""}
            try:
                if s["do"].startswith("Fill"):
                    fieldval = re.search(r"with `([^`]+)`", s["do"]).group(1)
                    loc = resolve(page, *s["locs"][0])
                    await loc.fill(fieldval)
                elif s["do"].startswith("Select"):
                    v = re.search(r"value `([^`]+)`", s["do"]).group(1)
                    await resolve(page, *s["locs"][0]).select_option(v)
                elif s["do"].startswith("Read"):
                    loc = resolve(page, *s["locs"][0])
                    fieldval = norm(await loc.inner_text())
                    result["returned_total"] = fieldval
                elif s["do"].startswith("Click"):
                    target = re.search(r"\*\*(.+?)\*\*", s["do"]).group(1)
                    used = None
                    for kind, args in s["locs"]:
                        loc = resolve(page, kind, args)
                        if await loc.count() == 1:
                            used = f"{kind}({args[:40]})"
                            await loc.first.click()
                            break
                    else:
                        # Playwright strict mode would raise on >1; skill says try fallbacks
                        for kind, args in s["locs"]:
                            loc = resolve(page, kind, args)
                            if await loc.count() >= 1:
                                used = f"{kind}({args[:40]}) FIRST-OF-{await loc.count()}"
                                await loc.first.click()
                                break
                        else:
                            raise RuntimeError(f"no locator resolved for {target!r}")
                    entry["detail"] = f"used {used}"
                    await page.wait_for_load_state("domcontentloaded")
                entry["status"] = "action-ok"
            except Exception as e:
                entry["status"] = "ACTION-ERROR"
                entry["detail"] = f"{type(e).__name__}: {str(e)[:120]}"
                result["steps"].append(entry)
                result["first_fail"] = {"step": s["n"], "where": "action", "detail": entry["detail"]}
                break
            # evaluate checks in order
            bad = None
            for c in s["checks"]:
                ok, why = await eval_check(page, c, fieldval)
                if not ok:
                    bad = (c, why)
                    break
            if bad:
                entry["status"] = "CHECK-FAIL"
                entry["detail"] = f"{bad[0]} -> {bad[1][:120]}"
                result["steps"].append(entry)
                result["first_fail"] = {"step": s["n"], "where": "check",
                                        "check": bad[0], "detail": bad[1]}
                break
            result["steps"].append(entry)
    finally:
        try:
            await ctx.close()
            await browser.close()
        except Exception:
            pass
    return result


VARIANTS = {
    "pristine": (ROOT / "skills/saucedemo_checkout.md", None),
    "a_step6": (ROOT / "tests/fixtures/saucedemo_checkout_item_tampered_a.md", None),
    "a_step5": (None, ("add-to-cart-sauce-labs-onesie", "add-to-cart-sauce-labs-bolt-t-shirt")),
    "b": (ROOT / "tests/fixtures/saucedemo_checkout_sort_tampered_b.md", None),
}


async def main():
    variant = sys.argv[1]
    path, repl = VARIANTS[variant]
    text = Path(path).read_text() if path else (ROOT / "skills/saucedemo_checkout.md").read_text().replace(*repl)
    async with async_playwright() as pw:
        pw.selectors.set_test_id_attribute("data-test")
        r = await run_skill(pw, text, variant)
    out = ROOT / f"reports/evidence/audit10_step_level_{variant}.json"
    out.write_text(json.dumps(r, indent=2))
    for s in r["steps"]:
        print(f"  step {s['n']:>2} {s['status']:<12} {s['do']}  {s['detail']}")
    ff = r["first_fail"]
    print(f"{variant}: returned_total={r['returned_total']} first_fail={ff}")
    print(f"evidence -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
