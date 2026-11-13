#!/usr/bin/env python
"""Fix 2, offline test: step 3's checks pin page content, not unstable site chrome.

Loads recordings/saucedemo_checkout/steps.json (no model, no browser) and asserts:
  - step 3 has no check whose testid contains "header", "sidebar" or "menu"
  - step 3 still anchors on the URL check (/inventory.html) + inventory-list
  - step count and step order are unchanged from the Fix 1 commit (a536619)

Run:  .venv/bin/python tests/acceptance/test_step3_checks.py
Exit 0 = all assertions held; nonzero = the check diff regressed.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEPS = json.loads((ROOT / "recordings/saucedemo_checkout/steps.json").read_text())

# Step sequence as recorded in the Fix 1 commit (a536619): same actions, same order.
FIX1_SEQUENCE = [(1, "fill"), (2, "fill"), (3, "click"), (4, "select"), (5, "click"),
                 (6, "click"), (7, "click"), (8, "click"), (9, "fill"), (10, "fill"),
                 (11, "fill"), (12, "click"), (13, "read"), (14, "click")]


def main():
    failures = []
    by_n = {s["n"]: s for s in STEPS}
    step3 = by_n[3]
    testids = [c["testid"] for c in step3["checks"] if c["type"] == "text"]
    chrome = [t for t in testids if any(w in t.lower() for w in ("header", "sidebar", "menu"))]

    if chrome:
        failures.append(f"step 3 checks chrome elements: {chrome}")
    print(f"  [{'PASS' if not chrome else 'FAIL'}] step 3 has no header/sidebar/menu check "
          f"(text checks: {testids})")

    has_url = any(c["type"] == "url" and c["value"] == "/inventory.html" for c in step3["checks"])
    has_list = "inventory-list" in testids
    if not (has_url and has_list):
        failures.append(f"step 3 anchors wrong: url check={has_url}, inventory-list check={has_list}")
    print(f"  [{'PASS' if has_url and has_list else 'FAIL'}] step 3 keeps URL (/inventory.html) "
          f"+ inventory-list checks")

    seq = [(s["n"], s["action"]) for s in STEPS]
    if seq != FIX1_SEQUENCE:
        failures.append(f"step sequence changed vs Fix 1 commit: {seq}")
    print(f"  [{'PASS' if seq == FIX1_SEQUENCE else 'FAIL'}] {len(STEPS)} steps, order unchanged "
          f"from Fix 1 commit (a536619)")

    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILURES")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: all step-3 check checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
