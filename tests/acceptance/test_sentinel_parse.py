#!/usr/bin/env python
"""Fix 1, offline test: the replayer's parse_result reads the skill's output contract.

Feeds sample agent replies (plain strings) to replayer.parse_result — no model, no browser.
Asserts the sentinel contract from the skill's "## Output" section:
  - success sentinel  `ORDER_TOTAL: $X.XX`       -> total as a float
  - tolerant fallback `Total: $X.XX`             -> total as a float
  - failure sentinel  `FAILED_STEP: <n>`         -> failed as an int (old `FAILED: step <n>` too)
  - prose with no sentinel                      -> total None

Run:  .venv/bin/python tests/acceptance/test_sentinel_parse.py
Exit 0 = all parse cases held; nonzero = a reply parsed wrong.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from replayer import parse_result  # noqa: E402  (product module, read-only use)

# (note, reply, expected total, expected failed)
CASES = [
    ("exact success sentinel at the end of the reply",
     "Checkout completed. The confirmation page says 'THANK YOU FOR YOUR ORDER'.\nORDER_TOTAL: $19.42",
     19.42, None),
    ("tolerated fallback: only a bare 'Total: $X.XX', no sentinel",
     "The overview page shows Item total: $17.98, Tax: $1.44. Total: $19.42. Done.",
     19.42, None),
    ("failure sentinel, new contract",
     "Step 5 check failed: cart badge expected '2', saw '1'. Giving up.\nFAILED_STEP: 5",
     None, 5),
    ("prose with no sentinel at all",
     "I finished the checkout flow and the order total looked reasonable.",
     None, None),
    ("old contract tolerated: 'FAILED: step <n>'",
     "Check failed after retry. FAILED: step 12",
     None, 12),
    ("failure sentinel without 'step' word",
     "Login page reappeared mid-flow. FAILED: 3",
     None, 3),
    ("'Subtotal:' must not parse as the total",
     "Subtotal: $17.98\nTax: $1.44\nTotal: $19.42",
     19.42, None),
]


def main():
    failures = []
    for note, reply, want_total, want_failed in CASES:
        r = parse_result(reply)
        ok = r == {"total": want_total, "failed": want_failed}
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failures.append(f"{note}: expected total={want_total} failed={want_failed}, got {r}")
        print(f"  [{mark}] {note}  ->  total={r['total']} failed={r['failed']}")

    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILURES")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: all sentinel parse checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
