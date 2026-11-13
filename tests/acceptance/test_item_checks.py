#!/usr/bin/env python
"""Fix 4, offline test: cart (step 7) and overview (step 12) checks pin FULL item names.

Loads recordings/saucedemo_checkout/steps.json (no model, no browser) and asserts:
  - steps 7 and 12 each demand both recorded items by their full, untruncated names
  - step count (14) and step order are unchanged
  - evaluating those checks against the wrong-second-item tamper fixture
    (tests/fixtures/saucedemo_checkout_item_tampered_a.md) fails at least one check

Item names are derived from the add-to-cart testid slugs, never hardcoded.

Run:  .venv/bin/python tests/acceptance/test_item_checks.py
Exit 0 = all assertions held; nonzero = a swapped item could still pass.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEPS = json.loads((ROOT / "recordings/saucedemo_checkout/steps.json").read_text())
FIXTURE = ROOT / "tests/fixtures/saucedemo_checkout_item_tampered_a.md"

FIX1_SEQUENCE = [(1, "fill"), (2, "fill"), (3, "click"), (4, "select"), (5, "click"),
                 (6, "click"), (7, "click"), (8, "click"), (9, "fill"), (10, "fill"),
                 (11, "fill"), (12, "click"), (13, "read"), (14, "click")]


def item_name(slug):
    """Same derivation as recorder._item_name: slug -> full display name."""
    return " ".join(w.capitalize() for w in slug.split("-"))


def recorded_items():
    """Items added to the cart, in recorded order, from the add-to-cart testids."""
    out = []
    for s in STEPS:
        tid = s["desc"].get("testid") or ""
        if s["action"] == "click" and tid.startswith("add-to-cart-"):
            out.append(item_name(tid[len("add-to-cart-"):]))
    return out


def item_checks(n):
    return [c["value"] for c in next(s for s in STEPS if s["n"] == n)["checks"]
            if c["type"] == "item_name"]


def main():
    failures = []
    items = recorded_items()
    print(f"  [note] recorded items (from add-to-cart testids): {items}")

    # 1. steps 7 and 12 each demand every full name, untruncated
    for n in (7, 12):
        got = item_checks(n)
        ok = got == items and not any("..." in v or v != v.strip() for v in got)
        if not ok:
            failures.append(f"step {n} item checks {got} != full names {items}, or truncated")
        print(f"  [{'PASS' if ok else 'FAIL'}] step {n} checks both full item names "
              f"(no truncation): {got}")

    # 2. step count and order unchanged
    seq = [(s["n"], s["action"]) for s in STEPS]
    ok = seq == FIX1_SEQUENCE
    if not ok:
        failures.append(f"step sequence changed: {seq}")
    print(f"  [{'PASS' if ok else 'FAIL'}] {len(STEPS)} steps, order unchanged")

    # 3. evaluate the checks against the wrong-second-item tamper fixture (offline:
    #    the fixture's Locator lines name what that skill would actually put in the cart)
    fxt = FIXTURE.read_text()
    fxt_slugs = []
    for tid in re.findall(r'add-to-cart-([a-z0-9-]+)', fxt):
        if tid not in fxt_slugs:
            fxt_slugs.append(tid)
    tampered_cart = [item_name(s) for s in fxt_slugs]
    page_text = " ".join(tampered_cart)  # the cart shows item names; containment = check passes
    results = {v: v in page_text for v in items}
    caught = not all(results.values())
    if not caught:
        failures.append(f"tampered cart {tampered_cart} passes all item checks: {results}")
    print(f"  [{'PASS' if caught else 'FAIL'}] tampered fixture cart {tampered_cart} -> "
          f"item checks {results} -> tamper CAUGHT")
    ok = all(v in " ".join(items) for v in items)  # honest cart passes all checks
    if not ok:
        failures.append(f"honest cart {items} fails its own checks")
    print(f"  [{'PASS' if ok else 'FAIL'}] honest cart {items} -> all item checks pass")

    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILURES")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: all item-name check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
