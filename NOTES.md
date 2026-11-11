# NOTES — what broke and how it got fixed

## Second rewrite: observed steps instead of a hardcoded list (2026-11-11)

**Broke:** the recorder wrote a hand-maintained `steps = [...]` list — nothing was actually
"recorded"; the recording was a transcription of the script that produced it. **Fixed:** an
injected init script listens for real `click`/`input`/`change` events (capture phase, so the
page snapshot is pre-action), each event target is described and located (data-test >
role+name > label > placeholder > text > css id), checks are derived by diffing before/after
page state, and the skill `.md` is rendered by the recorder from the observed steps.
Verified: two consecutive recorder runs produced byte-identical `steps.json`.

**Broke:** saving the storage state at the end of the run would carry the cart
(localStorage) into the next replay. **Fixed:** the session is saved right after login —
`ctx.storage_state()` immediately after `wait_for_url("**/inventory.html")`, before any cart
change.

**Broke:** `get_by_test_id` looks for `data-testid` by default; saucedemo uses `data-test`,
so every test-id locator would miss. **Fixed:** `pw.selectors.set_test_id_attribute("data-test")`
in both the recorder and the replay browser tools.

**Known-hardcoded / fragile (accepted for the demo):**

- Add-to-cart locators are item-specific (`add-to-cart-sauce-labs-onesie`,
  `add-to-cart-sauce-labs-bike-light`): "the two cheapest" lives in the step's intent text
  and the sort checks, not in the locator.
- Checks embed literal captured values, including the exact order total (`Total: $19.42`).
  Snapshot texts are truncated to 80 chars, capped at 5 checks per step, and taken in DOM
  order rather than by relevance. The read step's fallback locator
  (`get_by_text("Total: $19.42", exact=True)`) bakes the literal total in a second time.
- The demonstrator is still a script driving the browser — a human is simulated, not watched.
- The Goal and "When a check fails" sections of the skill come from `render_skill`'s
  template; only the steps themselves are observed.
- The login-skip rule ("skip steps 1-N") is a heuristic: every step that starts on the same
  URL as step 1 counts as login.
- The `get_by_role("button", name="Add to cart")` fallbacks match several buttons at once;
  if a primary test-id locator ever fails, the fallback trips Playwright's strict-mode limit.

**Fallout of the rewrite, fixed in the same pass:**

- `mcp_server.py` still imported the old `record()` / `skill_gen.generate()` — plain
  `ImportError`. Rewired to the new `recorder.record()`; `skill_gen.py` (old template
  pipeline) removed, since the recorder writes the skill itself.
- The tamper target in `run_pass_test.py` (`` `lohi` (Price: low to high) ``) no longer
  existed in the regenerated skill, so PASS 2 aborted at its assert. Retargeted to flipping
  `Select "Price (low to high)" (value \`lohi\`)` to `hilo` — caught by the step-4 derived
  checks.
- The tampered fixture moved from `skills/` to `tests/fixtures/` (it is a test input, not a
  skill the agent should normally read), and the Read guard in `hooks.py` now also allows
  `tests/fixtures/*.md` — otherwise the guarded agent could not read the fixture and PASS 2
  would fail for the wrong reason.

## First full run: the hardcoded-steps pipeline (2026-11-11)

### Breakage encountered and fixed

1. **`recorder.py` was gone.** The previous session never saved it — repo had zero commits and
   the file existed nowhere on disk. Rebuilt against the contract the other files impose:
   `record()` returns `{"total": ...}`, writes `artifacts/steps.json` with
   `{n, title, action, locator, check, on_fail}` per step, saves `artifacts/state.json`
   (storage state saved *after* checkout, so it's logged-in with an empty cart — the skill's
   stated precondition), and step 3's locator carries the exact string
   `` `lohi` (Price: low to high) `` that `run_pass_test.py` tampers.

2. **SauceDemo's checkout form uses camelCase test ids** (`firstName`, `lastName`,
   `postalCode`) while the rest of the site is kebab-case (`shopping-cart-link`,
   `product-sort-container`). First recorder run timed out filling `first-name` on
   checkout-step-one. Fixed ids in both the recorder actions and the recorded step 6 text.

3. **Tamper test had a hole in the skill text.** Step 3 originally named the option value in
   both the *Do* line and the *Locator* line; `run_pass_test.py` only rewrites the Locator, so
   an obedient agent following the *Do* line would still have sorted `lohi` and passed — the
   tamper would have gone undetected. Fix: the *Do* line now says "choose exactly the option
   named in the Locator", so the tampered Locator is the only source of truth. Verified:
   `lohi` occurs exactly once in the generated skill, and PASS 2 now fails at step 3 as
   intended.

### What worked first try

- The whole Agent SDK surface that was written from memory against the installed
  `claude-agent-sdk` (Python 3.14): `@tool(name, desc, {param: type})`,
  `create_sdk_mcp_server(name, version, tools)`, `HookMatcher(hooks=[...])`,
  the PreToolUse deny shape (`hookSpecificOutput.permissionDecision`), `SdkMcpTool.name`,
  and the `ClaudeAgentOptions` fields used (`mcp_servers`, `allowed_tools`,
  `disallowed_tools`, `hooks`, `max_turns`).
- SDK auth via the existing Claude Code login (no `ANTHROPIC_API_KEY` set).
- The nested-client pattern in `mcp_server.py`: a `ClaudeSDKClient` created inside an MCP
  tool callback of another client ran the full replay without deadlock.

### Observed behavior worth keeping

- The replay agent's first move was to try `Read artifacts/state.json`; the guard hook denied
  it and the agent adapted to `browser_load_session` — exactly the design intent. 21 tool
  calls logged in `logs/tool_calls.jsonl`, 1 blocked.
- `logs/network.jsonl` caught checkout-phase requests via the `/checkout-` URL substring
  (e.g. the thank-you checkmark image on `checkout-complete.html`).

### Quirk

- The SDK-spawned CLI logs `[claude-code:unrecognized_model]` for this environment's model
  name and falls back to its default. Harmless, but the replay agent's model is whatever the
  CLI defaults to — pass `model=` in `ClaudeAgentOptions` to pin it.

### Still open

- The brief's harder option is not implemented: no deliberately failing request with the
  retry rule recovering. `logs/network.jsonl` logging (the easier option) is what ships.
