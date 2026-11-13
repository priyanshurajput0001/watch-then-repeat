# watch-then-repeat

## Quick start

1. Record once: `.venv/bin/python recorder.py`, which writes skills/saucedemo_checkout.md.
2. Replay with the agent: `.venv/bin/python replayer.py`, which reads only the skill file and prints the order total (ORDER_TOTAL: $X.XX).

Watch a browser workflow once, turn what was actually observed into a skill file, and let an
Agent SDK agent repeat it using nothing but that file. Demo workflow: a saucedemo.com
checkout — login, sort by price (low to high), add the two cheapest items, check out, read
the order total.

`recorder.py` drives the site once with a scripted demonstrator while an injected init script
listens to real DOM events (capture phase, so page snapshots are pre-action). From those
events it derives steps, locators, and checks, and writes `skills/saucedemo_checkout.md` —
the only file the replay agent reads. `replayer.py` is a Claude Agent SDK agent with eight
browser MCP tools and a PreToolUse guard hook; it follows the skill, verifies each check,
and ends its reply with a sentinel line: `ORDER_TOTAL: $X.XX` on success, `FAILED_STEP: <n>`
on failure. Everything is regenerated from the recording — two recorder runs in a row
produce byte-identical `steps.json` and skill files (verified repeatedly this session).

## Setup

Repo root as working directory. Python 3.14 (built and run on 3.14.7).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # playwright + claude-agent-sdk
.venv/bin/playwright install chromium
```

Auth: the SDK reuses an existing Claude Code login; there is no API key in the repo and none
needs to be exported. `HEADED=1` before a replay command shows the browser.

## Run

```bash
.venv/bin/python recorder.py
# -> wrote recordings/saucedemo_checkout/ (14 steps, total Total: $19.42) and skills/saucedemo_checkout.md

.venv/bin/python replayer.py
# -> agent replays the skill in a real browser; last lines:
#    ORDER_TOTAL: $19.42 / TOTAL: 19.42 | FAILED STEP: None

.venv/bin/python mcp_server.py
# -> MCP demo: one agent calls record_workflow then replay_workflow; reports both totals ($19.42).

.venv/bin/python run_pass_test.py
# -> run 1: total=19.42 failed=None
#    run 2: total=19.42 failed=None
#    PASS 1 (same total twice): True
#    tampered: total=None failed=4
#    PASS 2 (check caught the change): True

bash tests/acceptance/run_audit.sh             # deterministic phases only (~15 min, no model; not executable, run via bash)
bash tests/acceptance/run_audit.sh --with-replays   # adds 6 agent replays (~60-90 min)
# -> per-phase PASS output; ends "Deterministic phases done (FAILURES=0)."
```

Replays need a fresh session: the saucedemo cookie expires after ~10 minutes. Refresh it
first (scripted login, no model; also verifies logged-in + empty cart):

```bash
.venv/bin/python tests/acceptance/refresh_session.py   # -> "VERDICT": "logged-in, cart EMPTY"
```

Offline tests (no model, no browser or local-only):

```bash
tests/acceptance/test_skill_structure.py   # skill sections, per-step checks, sentinel contract, no re-save wording
tests/acceptance/test_sentinel_parse.py    # 7 parse cases for ORDER_TOTAL / FAILED_STEP
tests/acceptance/test_step3_checks.py      # step 3 = URL + inventory-list, no header/sidebar/menu checks
tests/acceptance/test_item_checks.py       # steps 7/12 demand full item names; wrong-item tamper caught
tests/acceptance/test_offsite_block.py     # is_allowed_url unit cases + live loopback abort/popup-close
tests/acceptance/test_hooks_unit.py        # 25-case navigation URL matrix, Read guard, log shape
```

## MCP tools

`mcp_server.py` exposes two tools over `create_sdk_mcp_server`:
- `record_workflow` — runs the recorder; returns `recorded; skill file at skills/saucedemo_checkout.md; recorded total Total: $19.42`.
- `replay_workflow` — runs the replay agent; returns `total=$19.42 failed_step=None` (or `failed_step=<n>`).

`browser_tools.py` is the MCP server the replay agent itself gets: `browser_load_session`
(start from `artifacts/state.json`), `browser_goto`, `browser_click`, `browser_fill`,
`browser_select`, `browser_read_text`, `browser_all_texts`, `browser_url`. Each returns a
short status line (`at <url>`, `clicked; url=<url>`, element text, page URL). All requests
run through a context-level allowlist: non-saucedemo requests are aborted and logged to
`logs/network.jsonl`; off-site popups are closed.

## Layout

| file | role |
|---|---|
| `recorder.py` | DOM-event observer + scripted demonstrator; steps -> locators -> derived checks -> skill .md |
| `replayer.py` | the guarded replay agent; parses the sentinel from the final reply |
| `browser_tools.py` | the agent's 8 browser tools; context-level off-site request abort + popup guard |
| `hooks.py` | PreToolUse hook: logs every call, blocks non-saucedemo `browser_goto`, restricts `Read` to `skills/*.md` and `tests/fixtures/*.md` |
| `mcp_server.py` | record_workflow / replay_workflow as MCP tools + demo |
| `run_pass_test.py` | the two pass criteria (same total twice; tampered skill caught) |
| `skills/` | generated skill files — the replay agent's only input |
| `recordings/` | `steps.json` (observed steps) + `trace.zip` per recording |
| `artifacts/` | gitignored; `state.json` session storage, regenerated by every recorder run |
| `logs/` | `tool_calls.jsonl` (every tool call, blocked or not), `network.jsonl` (checkout requests + blocked requests) |
| `tests/` | offline acceptance tests, tamper fixtures, audit runner |
| `reports/` | QA report and evidence |

## How the brief's requirements are met

- **Locators**: priority `data-test` > role+name > label > placeholder > text > css id, with fallbacks per step (`recorder.py pick_locators`).
- **Checks**: derived by diffing before/after snapshots, capped at 5, chrome (header/menu/sidebar) excluded; step 3 anchors on URL + `inventory-list`; steps 7/12 add full item-name checks (`recorder.py derive_checks`, `add_item_name_checks`).
- **Session handling**: storage state saved right after login, before any cart change (`recorder.py`); replay loads it via `browser_load_session`; skill skips login steps when valid (`render_skill`).
- **Navigation hook**: `browser_goto` to non-saucedemo hosts denied by the PreToolUse hook (`hooks.py`), plus a context-level route that aborts off-site requests and closes off-site popups (`browser_tools.py`).
- **Logging hook**: every tool call appended to `logs/tool_calls.jsonl` with tool, input, timestamp, blocked flag (`hooks.py`).
- **Network interception**: requests on `/checkout-*` pages logged to `logs/network.jsonl` (`browser_tools.py _route`).
- **Pass test**: same total twice (PASS 1), then the tampered `lohi`->`hilo` skill must return no total and a failed step (PASS 2). Final run: PASS 1 True (19.42 twice) and PASS 2 True (tampered run stopped at step 4: `total=None failed=4`), enforced by the hard stop rule plus strict sort checks (`run_pass_test.py`).
- **Tamper test**: wrong-item and altered-check fixtures under `tests/fixtures/`; `test_item_checks.py` evaluates the wrong-item one offline against the item-name checks (caught).

## Known limits

- The saucedemo session cookie expires after ~10 minutes; runs longer than that fall back to a fresh login mid-flow.
- Add-to-cart locators are item-specific (`add-to-cart-sauce-labs-onesie`, `add-to-cart-sauce-labs-bike-light`); "two cheapest" lives in the sort + intent, not the locator. The tamper now fails the strict step 4 checks and the hard stop rule ends the run, but a cleverer agent could still reason past a stop instruction.
- Only the easier network option ships: request logging on checkout pages. No deliberately failing request with retry recovery.
- The replay model is whatever the local CLI defaults to (the SDK logs `unrecognized_model` for this environment); it is not pinned.
- The MCP demo's outer agent is not tool-restricted beyond `allowed_tools`; `Bash` is not in its disallowed list.
