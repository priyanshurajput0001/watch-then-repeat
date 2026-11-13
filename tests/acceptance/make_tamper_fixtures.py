#!/usr/bin/env python
"""QA audit: generate tampered skill fixtures under tests/fixtures/ (the Read guard only
lets the agent read skills/*.md and tests/fixtures/*.md).

  total_tampered  (task 4)   every literal "Total: $19.42" -> "Total: $88.88"
  repo_tampered   (task 10)  the repo's own tamper, regenerated exactly like run_pass_test.py
  check_tampered  (task 10c) step 5 check "shows \"1\"" -> "shows \"3\"" (action untouched)
  item_tampered_a (task 10a) step 6 Locator+css-id fallback bike-light -> bolt-t-shirt
                             (Do line untouched: still says Add to cart)
  sort_tampered_b (task 10b) sort option flipped in the Do line AND in any Locator/Fallback
                             line that mentions it (grep first: it appears ONLY in the Do line)

Each fixture asserts its replacement actually happened (>=1 occurrence).
Run: .venv/bin/python tests/acceptance/make_tamper_fixtures.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = (ROOT / "skills/saucedemo_checkout.md").read_text()
OUT = ROOT / "tests/fixtures"


def write(name, text):
    p = OUT / name
    p.write_text(text)
    print(f"wrote {p} ({len(text)} bytes)")


def sub_once(text, old, new, label):
    n = text.count(old)
    assert n >= 1, f"{label}: pattern not found: {old!r}"
    print(f"  {label}: {n} occurrence(s) replaced")
    return text.replace(old, new)


total_t = sub_once(SKILL, "Total: $19.42", "Total: $88.88", "task4 total")
write("saucedemo_checkout_total_tampered.md", total_t)

repo_t = sub_once(SKILL, 'Select "Price (low to high)" (value `lohi`)',
                  'Select "Price (high to low)" (value `hilo`)', "task10 repo tamper")
write("saucedemo_checkout_repo_tampered.md", repo_t)

check_t = sub_once(SKILL, '   - Check: `[data-test="shopping-cart-link"]` shows "1"',
                   '   - Check: `[data-test="shopping-cart-link"]` shows "3"', "task10c altered check")
assert check_t.count('shows "3"') >= 1
write("saucedemo_checkout_check_tampered.md", check_t)

item_t = sub_once(SKILL, 'add-to-cart-sauce-labs-bike-light', 'add-to-cart-sauce-labs-bolt-t-shirt',
                  "task10a wrong item locator (Locator + css-id fallback)")
assert 'add-to-cart-sauce-labs-bike-light' not in item_t
write("saucedemo_checkout_item_tampered_a.md", item_t)

sort_b = sub_once(SKILL, 'Select "Price (low to high)" (value `lohi`)',
                  'Select "Price (high to low)" (value `hilo`)', "task10b Do line")
n_loc = sort_b.count('lohi')
print(f"  task10b: lohi occurrences left in Locator/Fallback lines after Do-line flip: {n_loc} "
      f"(grep shows the option value never appears in any Locator line -> nothing else to flip)")
write("saucedemo_checkout_sort_tampered_b.md", sort_b)

# evidence: where does the sort option appear in the pristine skill?
import re
lines = SKILL.splitlines()
hits = [(i + 1, l.strip()) for i, l in enumerate(lines) if "lohi" in l or "Price (low to high)" in l]
out = ROOT / "reports/evidence/audit10_sort_option_occurrences.txt"
out.write_text("\n".join(f"line {n}: {l}" for n, l in hits) + "\n")
print(f"evidence -> {out}")
