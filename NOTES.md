# NOTES

## 1. What broke, and how it was fixed

- **recorder.py lost with no commits.** It existed nowhere on disk at the start; rebuilt against the contracts the other files impose.
- **data-test vs data-testid.** First run: every test-id locator missed. saucedemo uses `data-test`; fixed with `set_test_id_attribute("data-test")` in recorder.py and browser_tools.py.
- **camelCase checkout ids.** First run: filling `first-name` timed out — the ids are `firstName`/`lastName`/`postalCode`.
- **Cart leaking through storage state.** Saving the session at run end would carry the cart (localStorage) into the next replay; it is now saved right after login, before any cart change.
- **Off-site clicks.** Found by the audit: the guard hook only checked `browser_goto`. Fixed at the browser layer: a context-level route aborts non-saucedemo requests (logged to `logs/network.jsonl`) and off-site popups are closed.
- **Step 3 menu text.** Found by the audit (defect 2): the login step's checks embedded a transient burger-menu DOM flash and could never pass. Fixed: header/menu/sidebar testids are dropped from derived checks; step 3 anchors on the URL plus `inventory-list`.
- **Wrong second item.** Found by the audit (defect 4): cart checks pinned badge counts and 80-char truncated text. Fixed: the cart and overview steps demand each recorded item's full name.
- **Hardcoded steps list.** Found during early runs (the audit confirmed it): the "recording" was a transcription of its own script. Rewritten to observe real DOM events, describe and locate each target, and derive checks by diffing before/after snapshots. Two recorder runs now give byte-identical output.
- **ORDER_TOTAL contract.** Found by the audit (defect 1): the replayer parsed sentinels the skill never defined, so every replay returned total=None. The skill now ends replies with `ORDER_TOTAL: $X.XX` on success or `FAILED_STEP: <n>` on failure, and the replayer parses both (tolerating a bare `Total:` fallback).
- **Agent continuing after a failed check.** Found by a pass test: a tampered (sort flipped to high-to-low) replay read the failing sort check, continued to checkout anyway, and returned a total. Fixed with a hard stop rule in the skill ("STOP IMMEDIATELY ... `FAILED_STEP: <n>` and no ORDER_TOTAL line"), the same rule in the replayer's system prompt, and strict step 4 checks (active option equality; first price lower than second). The re-run stopped at step 4.
- **_ok regression.** An edit for the off-site block dropped the `_ok` helper, so every browser tool raised NameError at call time; the offline tests missed it because they bypass the tool wrappers. Found when the replayer and MCP demo failed during verification runs; fixed by restoring the helper.
- **Tamper hole.** The tamper test rewrote only the Locator line, so an agent following the Do line would still sort correctly and the tamper would go unnoticed. Fixed by making the Locator the only source of the sort option.

## 2. What I verified (real numbers)

- PASS 1: `run 1: total=19.42 failed=None`, `run 2: total=19.42 failed=None` — seven clean replays, all $19.42.
- PASS 2 (final run): the tampered replay stopped at step 4 — `total=None failed=4`, `PASS 2: True`.
- Hook unit tests: 33/33 PASS — 25-case navigation matrix, 8 Read-guard cases, log shape; host matching is `urlparse` hostname equality/suffix.
- Audited verification replay: total $19.42, 250.3s, 31 tool calls; hook-log reconcile 31=31, sequences identical, 0 blocked.
- Offline suites: sentinel parse 7/7; off-site block 12 unit cases + live loopback (0 requests reached the server, popup closed); step-3 checks 3/3; item checks including the tamper caught; skill structure all PASS.
- Recorder determinism: steps.json and skill byte-identical across double runs. MCP demo: recorded $19.42, replayed $19.42.

## 3. What I would change next

- Make the demonstrator a real human recording, not a script.
- Remove literal values from checks (the embedded total; checks still embed captured values such as step 4's prices and the option label).
- Replace item-specific add-to-cart locators with an intent-based "two cheapest" rule — the tamper would then actually change the cart.
- Implement the harder network option: a deliberately failing request with the retry rule recovering it (fail the first attempt, allow bounded retries with each attempt logged, order total unchanged, behind a flag so default runs stay deterministic).
- Add a tool to re-save the session mid-flow.
- Pin the replay model (`model=` in ClaudeAgentOptions).
- Point run_replay.py's duplicated parse at `replayer.parse_result`; the outer MCP demo agent is still unrestricted (`mcp_server.py` sets only `allowed_tools`, no `disallowed_tools`) — add it there.
