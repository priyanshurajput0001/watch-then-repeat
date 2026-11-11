# watch-then-repeat

Watch a browser workflow once, turn it into a skill file, and let an agent repeat it —
guarded, deterministic, and verifiable. Demo target: https://www.saucedemo.com (the Sauce
Labs demo store; demo credentials only).

## Flow

```
recorder.py        one scripted run: login -> sort lohi -> buy 2 cheapest -> checkout -> thank you
                   writes artifacts/steps.json (step script) + artifacts/state.json (logged-in, empty-cart session)

skill_gen.py       artifacts/steps.json -> skills/saucedemo_checkout.md  (the ONLY file the replay agent reads)

replayer.py        Claude Agent SDK agent, skills/saucedemo_checkout.md as its brief, 8 browser MCP
                   tools, PreToolUse guard hook. Prints ORDER_TOTAL.

run_pass_test.py   PASS 1: replay twice -> identical total?
                   PASS 2: tamper the sort option in the skill -> does a step check catch it?

mcp_server.py      exposes record_workflow / replay_workflow as MCP tools; demo runs record + replay.
```

## Files

| file | role |
|---|---|
| `recorder.py` | sync Playwright, records steps + session state |
| `skill_gen.py` | steps.json -> skill markdown |
| `browser_tools.py` | the replay agent's only browser tools (async Playwright, `data-test` ids, checkout request logging) |
| `hooks.py` | PreToolUse hook: logs every call, blocks non-saucedemo navigation, restricts `Read` to `skills/*.md` |
| `replayer.py` | the guarded replay agent |
| `mcp_server.py` | record/replay as MCP tools + demo |
| `run_pass_test.py` | the two pass criteria |
| `logs/tool_calls.jsonl` | every tool call, blocked or not |
| `logs/network.jsonl` | every request made on `/checkout-*` pages |

## Run

```bash
python recorder.py          # artifacts/ + session
python skill_gen.py         # skills/saucedemo_checkout.md
python replayer.py          # agent replays, prints TOTAL
python run_pass_test.py     # both pass tests
python mcp_server.py        # MCP demo: record + replay through the tools
```

Requires the repo's `.venv` (playwright + claude-agent-sdk; chromium already installed) and SDK
auth — either `export ANTHROPIC_API_KEY=...` or an existing Claude Code login (the SDK reuses it).
`HEADED=1 python replayer.py` to watch the browser.

## Pass criteria (measured 2026-11-11)

- PASS 1 — two independent replays both returned `$19.42` -> **True**
- PASS 2 — tampered skill sorted `hilo`; step 3's price-order check caught it, agent replied
  `FAILED: step 3` and returned no total -> **True**
- Guard hook — the replay agent tried to `Read` `artifacts/state.json` (not under `skills/`),
  was denied, and fell back to `browser_load_session` as the skill instructs.
