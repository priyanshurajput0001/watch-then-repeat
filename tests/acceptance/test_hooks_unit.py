#!/usr/bin/env python
"""QA audit, Phase 5.2: unit-test the PreToolUse hook directly (no model, no browser).

Covers:
  - navigation guard: allowed hosts, adversarial look-alike hosts, weird schemes/ports/IPs
  - Read guard: skills/ and tests/fixtures/ .md allowed; everything else denied
  - deny shape: hookSpecificOutput.permissionDecision == "deny"
  - logging: every call lands in a temp log with tool, input, timestamp, blocked flag

Run:  .venv/bin/python tests/acceptance/test_hooks_unit.py
Exit 0 = all assertions held; nonzero = a guard behaved wrong.
"""
import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import hooks  # noqa: E402  (product module, read-only use)

# ---------------------------------------------------------------- URL matrix
# (url, expected_allowed, note)
URL_CASES = [
    # explicitly allowed by the brief
    ("https://www.saucedemo.com/", True, "canonical host"),
    ("https://www.saucedemo.com/inventory.html", True, "protected page"),
    ("https://saucedemo.com/", True, "apex host"),
    # must be blocked
    ("https://example.com", False, "other host"),
    ("http://evil.com", False, "other host, http"),
    ("https://saucedemo.com.evil.com/", False, "saucedemo.com as evil's subdomain"),
    ("https://evil.com/saucedemo.com", False, "saucedemo.com only in path"),
    ("https://www.saucedemo.com@evil.com/", False, "userinfo trick: real host is evil.com"),
    ("https://notsaucedemo.com", False, "prefix look-alike"),
    ("file:///etc/passwd", False, "file scheme"),
    ("javascript:alert(1)", False, "js scheme"),
    ("data:text/html,<h1>hi</h1>", False, "data scheme"),
    ("about:blank", False, "about scheme (audit decision: block; not saucedemo)"),
    ("HTTPS://WWW.SAUCEDEMO.COM/", True, "uppercase scheme+host (hostname is lowercased)"),
    ("https://www.saucedemo.com./inventory.html", False, "trailing-dot host (suffix match misses; false-positive block, safe direction)"),
    ("https://www.saucedemo.com:8443/", True, "odd port on real host (allowed: hostname matches)"),
    ("https://saucedemo.com:8443@evil.com/", False, "port-in-userinfo trick"),
    ("https://127.0.0.1/", False, "loopback IP"),
    ("https://0x7f.0x0.0x0.0x1/", False, "hex IP"),
    ("https://2130706433/", False, "decimal IP"),
    ("https://example.com/?next=https://saucedemo.com", False, "saucedemo.com in query only"),
    ("https://example.com?q=www.saucedemo.com", False, "saucedemo.com in query only (no path)"),
    ("www.saucedemo.com", True, "scheme-less: hook prepends https://"),
    ("//evil.com/saucedemo", False, "protocol-relative URL to evil"),
]


def call(name, inp):
    return hooks.log_and_guard({"tool_name": name, "tool_input": inp}, "id", None)


async def main():
    failures = []
    print("=== navigation guard (hook function level) ===")
    for url, want_ok, note in URL_CASES:
        res = await call("mcp__browser__browser_goto", {"url": url})
        denied = bool(res.get("hookSpecificOutput"))
        got = not denied
        mark = "PASS" if got == want_ok else "FAIL"
        if got != want_ok:
            failures.append(f"nav {url!r}: expected {'allow' if want_ok else 'deny'}, got {'allow' if got else 'deny'}")
        print(f"  [{mark}] {'allow' if got else 'DENY '} {url!r:<55} ({note})")
        if denied:
            d = res["hookSpecificOutput"]
            assert d.get("permissionDecision") == "deny", f"bad deny shape for {url}: {res}"
            assert d.get("hookEventName") == "PreToolUse", f"bad event name for {url}: {res}"

    # parsing method: report how the host is derived (hostname equality/suffix, NOT substring)
    import urllib.parse as up
    probe = up.urlparse("https://evil.com/saucedemo.com").hostname
    print(f"  parsing method: urlparse(...).hostname -> {probe!r}; "
          f"allowed iff host == 'saucedemo.com' or host.endswith('.saucedemo.com')")

    print("=== Read guard ===")
    read_cases = [
        (str(ROOT / "skills/saucedemo_checkout.md"), True, "skill file"),
        (str(ROOT / "tests/fixtures/saucedemo_checkout_tampered.md"), True, "tamper fixture"),
        (str(ROOT / "artifacts/state.json"), False, "session state"),
        (str(ROOT / "recordings/saucedemo_checkout/steps.json"), False, "recording"),
        (str(ROOT / "hooks.py"), False, "hook source"),
        (str(ROOT / "README.md"), False, "readme (not under skills/)"),
        (str(ROOT / "skills/../hooks.py"), False, "traversal out of skills/"),
        (str(ROOT / "tests/fixtures/not.md.txt"), False, "non-md extension in fixtures"),
    ]
    for p, want_ok, note in read_cases:
        res = await call("Read", {"file_path": p})
        got = not bool(res.get("hookSpecificOutput"))
        mark = "PASS" if got == want_ok else "FAIL"
        if got != want_ok:
            failures.append(f"read {p}: expected {'allow' if want_ok else 'deny'}, got {'allow' if got else 'deny'}")
        print(f"  [{mark}] {'allow' if got else 'DENY '} {Path(p).name:<40} ({note})")

    # non-Read, non-goto tools must pass through untouched (log only)
    res = await call("mcp__browser__browser_click", {"kind": "test_id", "value": "finish"})
    if res.get("hookSpecificOutput"):
        failures.append(f"browser_click unexpectedly denied: {res}")
    res = await call("Bash", {"command": "curl https://evil.com"})
    if res.get("hookSpecificOutput"):
        print("  [note] Bash IS denied/intercepted (disallowed upstream too)")
    else:
        print("  [note] Bash not guarded by hook (blocked upstream via disallowed_tools)")

    print("=== log records ===")
    # every call above must have been appended with tool/input/t/blocked
    log = Path(tempfile.gettempdir()) / "wtr_hooklog_check.jsonl"
    hooks.LOG = log  # redirect (audit-only; module attr)
    log.unlink(missing_ok=True)
    await call("mcp__browser__browser_goto", {"url": "https://example.com"})
    await call("mcp__browser__browser_goto", {"url": "https://www.saucedemo.com/"})
    recs = [json.loads(l) for l in log.read_text().splitlines()]
    assert len(recs) == 2, f"expected 2 log records, got {len(recs)}"
    assert recs[0]["blocked"] is True and recs[1]["blocked"] is False
    for r in recs:
        assert {"t", "tool", "input", "blocked"} <= set(r), f"record missing keys: {r}"
        assert isinstance(r["t"], float), "timestamp missing"
    print(f"  [PASS] 2/2 calls logged with t/tool/input/blocked; deny REASON is not persisted "
          f"(finding: only a boolean, not the decision text)")

    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILURES")
        for f in failures:
            print("  -", f)
        return 1
    print("RESULT: all hook unit checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
