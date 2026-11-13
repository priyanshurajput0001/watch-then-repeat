# NOTES

## 1. What broke, and how I fixed it

- **recorder.py lost with no commits.** Found at the 2026-11-11 session start: zero commits, file
  nowhere on disk. Rebuilt against the contracts the other files impose.
- **data-test vs data-testid.** Found on the first recorder run: every test-id locator missed.
  saucedemo uses `data-test`; Playwright defaults to `data-testid`. Fixed with
  `set_test_id_attribute("data-test")` in recorder.py and browser_tools.py.
- **camelCase checkout ids.** Found on the first run: fill of `first-name` timed out — the ids
  are `firstName`/`lastName`/`postalCode`. Fixed in the demonstrator actions.
- **Hardcoded steps list.** Found by the QA audit (reports/QA_REPORT.md): the "recording" was a
  transcription of its own script. Fixed by the observed-events rewrite (init script listens to
  real clicks/inputs; checks diff before/after snapshots). Verified: two recorder runs produce
  byte-identical steps.json and skill.
- **Tamper hole: the Do line named the option.** Found by the audit (task 10b): `lohi` appeared
  in the skill's Do line, so a literal flip of the locator left the Do line — or vice versa —
  still satisfiable. Fixed: the option now comes only from the step's locator line.
- **Cart leaking through saved storage state.** Found while placing the session save: saving at
  run end would carry the cart (localStorage) into the next replay. Fixed: save right after
  login, before any cart change.
- **ORDER_TOTAL sentinel never defined.** Found by the audit (defect 1): replayer.py parsed
  sentinels the skill never defined, so every replay returned total=None. Fixed (Fix 1): the
  skill gained an Output section (`ORDER_TOTAL: $X.XX` / `FAILED_STEP: <n>`), replayer gained a
  tolerant `parse_result`. Verified by a real replay ending `ORDER_TOTAL: $19.42`.
- **Transient menu-open text in step 3 checks.** Found by the audit (defect 2): the login step's
  checks embedded a burger-menu DOM flash and could never pass; fresh-login replays R4/R5
  halted there. Fixed (Fix 2): header/menu/sidebar testids are filtered out of derived checks;
  step 3 anchors on URL + `inventory-list`. Fresh login now passes step 3 (seen in this
  session's pass-test run 3).
- **Off-site clicks not blocked.** Found by the audit (defect 3): the hook guarded only
  `browser_goto`; the route handler never aborted. Fixed (Fix 3): context-level route aborts
  non-saucedemo requests and off-site popups are closed. Regression from that fix: the edit
  dropped the `_ok` helper, so every browser tool raised `NameError` — found by this session's
  verification runs (MCP demo and direct replay failed with `name '_ok' is not defined`; the
  offline tests missed it because they bypass the tool wrappers), fixed by restoring the helper.
- **Wrong second item passing the checks.** Found by the audit (defect 4): cart checks pinned
  badge counts and 80-char truncated text. Fixed (Fix 4): steps 7 (cart) and 12 (overview)
  demand each recorded item's full name; `test_item_checks.py` evaluates the wrong-item tamper
  fixture offline and it is caught.
- **The agent kept going after a failed check.** Found by this session's pass test: the tampered
  (`lohi`->`hilo`) replay read the failing sort check, continued to checkout anyway, and returned
  19.42 (PASS 2 False). Fixed: a hard stop rule in the skill template ("If a Check fails after
  one retry, STOP IMMEDIATELY ... `FAILED_STEP: <n>` and no ORDER_TOTAL line") and the same rule
  in the replayer's system prompt (a failed Check means an incorrect page state, not something
  to work around), plus strict step 4 checks (active option must equal "Price (low to high)";
  first item's price must be lower than the second's). Re-run: the tampered replay stopped at
  step 4 — `total=None failed=4`, PASS 2 True.
- **Unrestricted outer MCP agent.** Found by the audit (P2): the demo sets only `allowed_tools`.
  Confirmed live this session: during the demo the outer agent ran `Bash` and attempted `Read`s.
  Not yet fixed — `mcp_server.demo()` needs `disallowed_tools`; untouched by design this session.

## 2. What I verified (this session, real numbers)

- **PASS 1 (same total twice):** `run 1: total=19.42 failed=None`, `run 2: total=19.42
  failed=None`, `PASS 1: True`. Seven clean replays this session (verification replay, first
  pass test runs 1-2, post-repair MCP demo, final pass test runs 1-2, quick-start replayer) all
  returned $19.42.
- **PASS 2 (tamper caught): True in the final run.** After the hard stop rule + strict step 4
  checks, the tampered (`lohi`->`hilo`) replay stopped at step 4: `total=None failed=4`,
  `PASS 2 (check caught the change): True`. (The earlier pass test, before those changes, had
  returned `total=19.42 failed=None` — PASS 2 False; see section 1.)
- **Hook URL table:** `test_hooks_unit.py` 33/33 PASS — 25-case navigation matrix (userinfo,
  subdomain-lookalike, decimal/hex IP, protocol-relative tricks), 8 Read-guard cases, log-shape
  checks; host matching is `urlparse(...).hostname` equality/suffix.
- **Audited verification replay:** total $19.42, 250.3s, 31 tool calls; hook-log reconciliation
  31=31, sequences identical, 0 blocked.
- **Offline suites:** sentinel parse 7/7; off-site block 12 unit cases + live loopback (0
  requests reached the server, popup closed); step-3 checks 3/3; item checks incl. tamper
  caught; skill structure all PASS (incl. the no-re-save assertion).
- **Recorder determinism:** steps.json and skill byte-identical across double runs (re-verified
  in Fixes 1, 2, 4, 5). MCP demo (post-repair): recorded $19.42, replayed $19.42.

## 3. What I would change next

- Make the demonstrator a real human recording, not a script.
- Remove literal values from checks (the embedded total, menu texts); checks still embed
  captured values — for example step 4's recorded prices (`$7.99`, `$9.99`) and the option label.
- The outer MCP demo agent is still unrestricted: `mcp_server.py` sets only `allowed_tools` and
  no `disallowed_tools` (verified in the source), so the demo agent's `Bash` is not blocked.
- Replace item-specific add-to-cart locators with an intent-based "two cheapest" rule — this
  also removes PASS 2's blind spot, since the tamper would then actually change the cart.
- Implement the harder network option: a deliberately failing request with the retry rule
  recovering it.
- Add a tool to re-save the session mid-flow (the skill no longer promises it, but a >10-min
  run still ends with a stale state file).
- Pin the replay model (`model=` in ClaudeAgentOptions); PASS 2's instability argues for it.
- Point run_replay.py's duplicated parse at `replayer.parse_result`, and add `disallowed_tools`
  to the MCP demo agent.
