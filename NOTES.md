# NOTES — what actually broke, first full run (2026-11-11)

## Breakage encountered and fixed

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

## What worked first try

- The whole Agent SDK surface that was written from memory against the installed
  `claude-agent-sdk` (Python 3.14): `@tool(name, desc, {param: type})`,
  `create_sdk_mcp_server(name, version, tools)`, `HookMatcher(hooks=[...])`,
  the PreToolUse deny shape (`hookSpecificOutput.permissionDecision`), `SdkMcpTool.name`,
  and the `ClaudeAgentOptions` fields used (`mcp_servers`, `allowed_tools`,
  `disallowed_tools`, `hooks`, `max_turns`).
- SDK auth via the existing Claude Code login (no `ANTHROPIC_API_KEY` set).
- The nested-client pattern in `mcp_server.py`: a `ClaudeSDKClient` created inside an MCP
  tool callback of another client ran the full replay without deadlock.

## Observed behavior worth keeping

- The replay agent's first move was to try `Read artifacts/state.json`; the guard hook denied
  it and the agent adapted to `browser_load_session` — exactly the design intent. 21 tool
  calls logged in `logs/tool_calls.jsonl`, 1 blocked.
- `logs/network.jsonl` caught checkout-phase requests via the `/checkout-` URL substring
  (e.g. the thank-you checkmark image on `checkout-complete.html`).

## Quirk

- The SDK-spawned CLI logs `[claude-code:unrecognized_model]` for this environment's model
  name and falls back to its default. Harmless, but the replay agent's model is whatever the
  CLI defaults to — pass `model=` in `ClaudeAgentOptions` to pin it.

## Still open

- The brief's harder option is not implemented: no deliberately failing request with the
  retry rule recovering. `logs/network.jsonl` logging (the easier option) is what ships.
