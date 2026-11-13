#!/usr/bin/env python
"""QA audit, task 3: assert the skill file has the required sections and per-step checks.

Run: .venv/bin/python tests/acceptance/test_skill_structure.py [skill.md]
Exit 0 = all structural requirements present.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "skills/saucedemo_checkout.md"


def main():
    t = SKILL.read_text()
    checks = [
        ("Goal section", bool(re.search(r"^## Goal\b", t, re.M))),
        ("Preconditions section", bool(re.search(r"^## Preconditions\b", t, re.M))),
        ("Numbered steps", bool(re.search(r"^1\. ", t, re.M)) and bool(re.search(r"^14\. ", t, re.M))),
        ("Failure handling section", bool(re.search(r"^## When a check fails\b", t, re.M))),
        ("Fresh-login rule stated", "fresh login is needed" in t.lower()),
        ("Session file named", "artifacts/state.json" in t),
        ("Empty-cart precondition", "cart must be empty" in t.lower()),
        ("Domain restriction stated", "navigation within" in t.lower() or "never navigate outside" in t.lower()),
        ("No-sleep rule stated", "no fixed sleeps" in t.lower()),
    ]
    # per-step check lines: every numbered step body has at least one "Check:"
    m = re.search(r"^## Steps\b(.*?)^## When a check fails", t, re.M | re.S)
    steps_section = m.group(1) if m else t
    steps = re.findall(r"^(\d+)\. (.*?)(?=^\d+\. |\Z)", steps_section, re.M | re.S)
    missing = [n for n, body in steps if "- Check:" not in body]
    checks.append((f"Every step has >=1 Check line (steps found: {len(steps)})", not missing and len(steps) == 14))
    # sentinel for the replayer: does the skill ever define ORDER_TOTAL / FAILED format?
    checks.append(("Defines ORDER_TOTAL result format (expected False -> replayer regex bug)",
                   "ORDER_TOTAL" in t))
    checks.append(("Defines FAILED: step format (expected False -> replayer regex bug)",
                   "FAILED" in t))

    ok = True
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed if "expected False" not in name else True
    # locators per step
    locs = re.findall(r"^   - Locator: `page\.(\w+)\(", t, re.M)
    from collections import Counter
    print("  primary locator kinds:", dict(Counter(locs)))
    css = re.findall(r"^   - Fallback: `page\.locator\(", t, re.M)
    print(f"  CSS-id fallback lines: {len(css)}")
    print(f"RESULT: {'ALL STRUCTURAL REQUIREMENTS PRESENT' if ok else 'MISSING REQUIREMENTS'} ({SKILL})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
