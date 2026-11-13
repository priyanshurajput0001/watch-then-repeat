# QA Report — watch-then-repeat

Audit date: 2026-11-13 · Auditor: QA audit agent (Claude Code) · Scope: full brief, items 1–10.
Budget: **6/6 full agent replays used** (R1–R6). Recorder runs, SDK probes and step-level harness
runs are not agent replays. All evidence under `reports/evidence/`. One-command re-run:
`tests/acceptance/run_audit.sh` (add `--with-replays` to include the replay sequence).

---

## Executive summary (ready-to-submit: **NO — do not ship as-is**)

The core idea works and is honestly instrumented: recording is genuinely observed (byte-identical
re-runs, demonstrator changes propagate to steps+skill), locators are all unique `data-test`
primaries, the guard hook is correctly parsed and the agent is properly sandboxed (blocked reads,
no Bash/Write/WebFetch), and replays deterministically produce the real total **$19.42** with
fail-safe behavior on tampers. But the ship blockers are real: (1) the replayer parses
`ORDER_TOTAL:`/`FAILED:` sentinels that the regenerated skill never defines, so **every successful
replay extracts `total=None`** and `run_pass_test.py` prints `PASS 1/2: False` as shipped; (2) the
skill's step-3 checks bake in a transient menu-open DOM flash and are **unpassable on a normal
replay**, stalling fresh-login runs (R4, R5 halted at step 3); (3) the ~10-minute session cookie
reliably kills any run longer than 10 minutes mid-flow (recovered in R2/R3, at cost); (4) an
off-site **click** is not stopped by anything (only `browser_goto` is guarded — an x.com tab opened
freely); (5) the wrong-item cart tamper on the *second* add-to-cart completes all checks and
returns a wrong total ($25.90) — checks only pin the first item's 80-char text.

**Top 5 risks**
1. Result-extraction contract broken (`ORDER_TOTAL`/`FAILED` never defined in the skill) — every
   programmatic consumer of `replay()` sees `None`/`None`; pass criteria cannot pass.
2. Unpassable recorded checks (menu-open flash in step 3 snapshots) — any fresh-login replay can
   halt at step 3; also makes checks flaky for agents (three different behaviors across R3/R4/R5).
3. No off-site navigation enforcement at the browser layer — hook guards one tool only; route
   handler never aborts; social-link click navigated off-site in a new tab.
4. Wrong-item cart tampers on the second add are MISSED end-to-end (wrong total returned).
5. 10-min session cookie vs multi-minute agent deliberation → mid-run session death; skill says
   "re-save the session" but **no tool can save the session**.

---

## Verdict table (brief requirements)

| Requirement | Verdict | Evidence |
|---|---|---|
| Recorder (observed steps, determinism) | **PASS** | 2 clean-clone runs byte-identical; regenerated outputs == committed (`cmp` in `run_audit.sh` phase 1); demonstrator item change → steps+skill change (`reports/evidence/audit2_recorder/`, `audit2_demonstrator_change.diff`) |
| Locators (types, css/nth flags, multi-match) | **PASS** w/ flags | 14/14 primaries `get_by_test_id`; **no nth/nth-child anywhere**; 11 css-id last-resort fallbacks flagged; 4 fallbacks match >1 (steps 5/6 role/text "Add to cart" ×6/×5, step 7 `get_by_text("2")`) — `reports/evidence/locator_resilience_audit.out`, `locator_resilience.json` |
| Skill file structure | **PASS** w/ caveat | Goal/Preconditions/14 numbered steps/≥1 Check per step/failure handling/fresh-login rule/empty-cart/no-sleep all present (`tests/acceptance/test_skill_structure.py`). Caveat: step 3 checks embed menu-open flash → unpassable (R4/R5) |
| Session (logged-in, empty cart, fresh login) | **PARTIAL** | Loads logged-in with empty cart (`audit3_state_check.json`); fresh login works (R3: `$19.42`, `R3_fresh_login.transcript.txt`) but unreliable: no session-save tool; 10-min cookie; step-3 check wall |
| Replayer reads only the skill | **PASS** | Read guard blocks state.json/steps.json/source (`audit6_probe_restrictions.txt`; unit suite; R3/R5 in-flight `state.json` reads blocked, `reconcile_logs.py`); every run's only successful Reads are the skill/fixtures; Bash/Write/WebFetch absent from agent toolset |
| MCP tools | **PARTIAL** | `record_workflow`+`replay_workflow` each called exactly once through MCP, hook-logged (`audit7_mcp/tool_calls_R1_slice.jsonl`); **no zombie Playwright browsers** after (0 before/0 after, `audit7_browsers_*.txt`); but replay returns `total=None` on success, and the demo agent is unrestricted (14 `Bash` calls) |
| Logging hook | **PASS** | Every call logged incl. blocked; per-run transcript↔log reconciliation: 71/71, 81/81, 17/17, 22/22, 20/20, sequences match (`tests/acceptance/reconcile_logs.py`). Minor: only a boolean is persisted, deny *reason* is not |
| Nav-block hook | **PASS** at tool level / **FAIL** at browser level | Parsed matching: `urlparse().hostname` equality/suffix — not substring (`hooks.py:18-22`); all 24 URL cases correct (`audit5_hooks_unit.out`). Off-site **click** NOT stopped: x.com tab opened (`audit5_offsite_click.json`); route handler never aborts (`browser_tools.py:18-27`) |
| Network interception | **PARTIAL** | Installed at `browser_tools.py:38` (`ctx.route("**/*", _route)`), logs iff route-time page URL contains `/checkout-`. Same-run comparison: 16 listener requests, 1 checkout-phase, 1 logged, **0 missed, 0 unrelated** (`audit8_network_comparison.json`). Caveats: saucedemo is a client-side SPA (no per-checkout document requests to catch); gate misses in-flight requests during route transitions and any non-primary-tab traffic; would log third-party (backtrace/fonts) calls made while a checkout page is open |
| Pass test (identical totals, empty cart) | **PARTIAL** | Totals **identical and equal to the real page total**: $19.42 in R1 (log evidence), R2, R3 transcripts; cart verified empty at start (`audit3_state_check.json`; fresh login in R3). BUT parsed totals are `None` (sentinel bug) → `run_pass_test.py` as shipped prints `PASS 1: False` / `PASS 2: False`; not run as-is (would consume 3 of the 6-replay budget; its parts verified individually) |
| Tamper test | **PARTIAL** | Repo tamper at agent level (R5): halted at step 3 (unpassable checks) *before* the tampered sort step — tamper only diagnosed statically by the agent. Mechanism proven at step level: sort tamper caught at step 4 (`audit10_step_level_b.json`) |
| README / NOTES | **PASS** w/ gaps | Flow/run commands/roles accurate; SDK auth documented. Gaps: no venv-create/`pip install`/`playwright install chromium` steps (clean clone walkthrough, `run_audit.sh` phase 1); `trace.zip` drifts uncommitted on every `record()`; NOTES honestly discloses the multi-match fallbacks and embedded total |

---

## Hook URL table (`hooks._allowed_host`, `audit5_hooks_unit.out`)

Matching is **parsed**: `urlparse(url).hostname` lowercased, allowed iff equal to
`saucedemo.com` or a `.saucedemo.com` subdomain. **Not substring.**

| URL | Verdict | Why |
|---|---|---|
| `https://www.saucedemo.com/` | ALLOW (required) | hostname == www.saucedemo.com |
| `https://saucedemo.com/inventory.html` | ALLOW (required) | apex host |
| `https://example.com` | DENY (required) | other host |
| `https://saucedemo.com.evil.com` | DENY (required) | host is evil.com (suffix of evil, not of saucedemo) |
| `https://evil.com/saucedemo.com` | DENY (required) | saucedemo.com only in path; hostname evil.com |
| `https://www.saucedemo.com@evil.com/` | DENY (required) | userinfo trick: hostname = evil.com |
| `https://notsaucedemo.com` | DENY (required) | prefix look-alike, host equality/suffix only |
| `file:///etc/passwd` | DENY (required) | hostname empty |
| `javascript:alert(1)` | DENY (required) | hostname empty |
| `HTTPS://WWW.SAUCEDEMO.COM/` | ALLOW | hostname lowercased |
| `https://www.saucedemo.com:8443/` | ALLOW | port not part of hostname (audit: acceptable) |
| `https://www.saucedemo.com./inventory.html` | DENY | trailing-dot host misses suffix match — false-positive block, safe direction |
| `https://saucedemo.com:8443@evil.com/` | DENY | port-in-userinfo trick, host = evil.com |
| `https://127.0.0.1/`, hex/decimal IP forms | DENY | IP hosts |
| `https://example.com/?next=https://saucedemo.com` | DENY | host only in query |
| `www.saucedemo.com` (scheme-less) | ALLOW | hook prepends https:// |
| `//evil.com/saucedemo` | DENY | protocol-relative to evil |
| `data:text/html,…`, `about:blank` | DENY | no saucedemo host |

**Enforcement boundary.** The hook fires only on tool calls and only guards `browser_goto`
(`hooks.py:31`). An off-site **link click** goes through `browser_click`, which the hook does not
nav-guard, and the Playwright route handler (`browser_tools.py:18-27`) only *logs* on `/checkout-`
pages and always `continue_()`s — measured result: clicking the footer X/Twitter link opened
`x.com/saucelabs` (off-site tab) freely (`audit5_offsite_click.json`: `navigated_offsite: true`).
So: goto guard = hook; click/popup navigation = **nothing**. Route layer enforces nothing today.

## Per-run table (6/6 replay budget)

Cart empty at start of every run: state.json verified empty-cart (`audit3_state_check.json`); R3
fresh login starts cartless; R2's agent re-verified and *repaired* the cart after a mid-run cookie
death (removed 2 inherited items before continuing).

| Run | Skill | Path | Parsed total | Real total (transcript/log) | Failed step | Duration | Tool calls | Blocked |
|---|---|---|---|---|---|---|---|---|
| R1 | committed | via MCP `replay_workflow` | `None` ⚠ | **$19.42** (badge reads + log) | — | 175.9 s (inner) | 24 browser | 1 (state.json read) |
| R2 | committed | direct | `None` ⚠ | **$19.42** | — | 410.7 s | 71 | 0 |
| R3 | committed | state.json **deleted** → fresh login | `None` ⚠ | **$19.42** | — | 996.7 s | 81 | 1 |
| R4 | `Total: $19.42`→`$88.88` everywhere | direct | `None` | none read — stopped at step 3* | — (agent refused `$88.88`, reasoned real ≈ $19.42) | 326.8 s | 17 | 0 |
| R5 | repo tamper: sort→`hilo` | direct | `None` | none read — stopped at step 3* | — (tamper diagnosed statically) | 488.1 s | 22 | 1 |
| R6 | step-5 check `shows "1"`→`shows "3"` | direct | `None` | none read — stopped at step 5 (fail-safe) | step 5 (prose, not sentinel ⚠) | 225.7 s | 20 | 0 |

⚠ = `replayer.py:42-43` regexes matched nothing although the agent reported results/failures in
prose — the sentinel-format gap (fix P0). \* R4/R5 fresh-login runs hit the unpassable step-3
checks (menu-open flash) before reaching their tampered steps.

## Tamper table

| Tamper | Level | What happened | Verdict |
|---|---|---|---|
| Repo's own (sort `lohi`→`hilo`, Do line) | Agent (R5) | Halted at step 3 on the unpassable menu-open checks; never executed the sort; agent identified the tamper statically as self-contradictory | **PARTIAL** (failure caused by an unrelated check defect, not the tamper) |
| (a) wrong item — step 6 locator `bike-light`→`bolt-t-shirt` | Step-level harness | All 14 checks pass, workflow completes, returns `Total: $25.90` (real items: Onesie+Bolt T-Shirt) | **MISSED** — checks pin only the first cart item's 80-char text (`audit10_step_level_a_step6.json`) |
| (a′) wrong item — step 5 locator `onesie`→`bolt-t-shirt` | Step-level harness | Caught at step 12: summary-container check expects "QTYDescription 1 Sauce Labs Onesie…" | **CAUGHT** (late, step 12) (`audit10_step_level_a_step5.json`) |
| (b) sort option flipped in Do **and** Locator lines | Step-level harness | Caught at step 4 (`active-option`/`secondary-header` checks). Grep evidence: the option text appears **only** in the Do line — no Locator line carries it (`audit10_sort_option_occurrences.txt`), so the flip is effectively Do-line-only | **CAUGHT** (`audit10_step_level_b.json`) |
| (c) altered check, correct action (step-5 link check `"1"`→`"3"`) | Agent (R6) | Not detected as tamper by any mechanism; agent executed the correct action, failed the bogus check after the retry rule, stopped at step 5, returned no total — and *suspected tampering* in prose | **MISSED** as detection / fail-safe stop (`R6_check_tamper.transcript.txt`) |
| (task 4) embedded total `$19.42`→`$88.88` | Agent (R4) | Agent refused to return the embedded value, flagged it as inconsistent with the workflow (reasoned real ≈ $19.42), returned no total; run stalled at step 3* | **PARTIAL** — core property held (embedded value NOT returned), run blocked by unrelated step-3 defect |

Tamper verdict legend: CAUGHT = check/locator mismatch stops the run at/near the tampered step ·
MISSED = workflow completes (or stops for unrelated reasons) despite the tamper · CRASHED = n/a in
any run · PARTIAL = failure caused by an unrelated defect/timeout, per the brief.

---

## Proposed fixes (by priority)

**P0 — define the result contract in the skill (2 blockers, one diff).** The replayer parses
`ORDER_TOTAL:` / `FAILED: step N` (`replayer.py:42-43`) but the regenerated skill never states
that format, so successful replays return `None` and failures aren't machine-detectable.

```diff
--- a/recorder.py
+++ b/recorder.py
@@ def render_skill(steps, start_url, state_path, title="Workflow", result_name="order total"):
-    L += ["## When a check fails",
+    L += ["## Result format",
+          f"On success, reply with the {result_name} exactly as: `ORDER_TOTAL: <value>`.",
+          "If you must stop, reply with exactly: `FAILED: step <n>: <expected> vs <actual>`.",
+          "",
+          "## When a check fails",
```

**P0 — fix the unpassable login checks (menu-open flash).** `derive_checks` snapshots taken
immediately after the login click caught the sidebar mid-flash (open menu), so step 3's checks
describe a DOM state the recorded steps never reproduce (R4, R5 halted; R3 only passed by
improvising at DOM level).

```diff
--- a/recorder.py
+++ b/recorder.py
@@ def demonstrate(page, ctx, rec, state_path):
         page.get_by_test_id("login-button").click()
         page.wait_for_url("**/inventory.html")
+        # settle: the SPA briefly renders the sidebar open; snapshot only stable state
+        page.locator('[data-test="inventory-sidebar-link"]').wait_for(state="hidden")
```
Plus (same root cause): checks derived from any page *transition* should be re-verified after the
app settles — e.g. have `Observer.finish` drop text checks that don't reproduce on a settle pass.

**P1 — enforce the domain at the browser layer, not only on `browser_goto`.** Hook stays as belt;
route handler becomes the actual guard (also covers clicks, popups, iframes):

```diff
--- a/browser_tools.py
+++ b/browser_tools.py
@@ from pathlib import Path
+from urllib.parse import urlparse
@@ async def _route(route):
+    host = urlparse(route.request.url).hostname or ""
+    if not (host == "saucedemo.com" or host.endswith(".saucedemo.com")):
+        await route.abort()   # off-site click/popup/iframe: blocked at the network layer
+        return
     page = _S.get("page")
```

**P1 — add the session-save tool the skill already promises.** The skill says "re-save the
session" but no tool can (R2/R3 transcripts note it). 

```diff
--- a/browser_tools.py
+++ b/browser_tools.py
@@ async def browser_url(args):
@@     return _ok((await _page()).url)
+
+@tool("browser_save_session", "Persist the current logged-in storage state to artifacts/state.json.", {})
+async def browser_save_session(args):
+    ctx = (await _page()).context
+    await ctx.storage_state(path="artifacts/state.json")
+    return _ok("session saved")
@@-_TOOLS = [browser_load_session, browser_goto, browser_click, browser_fill, browser_select,
-          browser_read_text, browser_all_texts, browser_url]
+_TOOLS = [browser_load_session, browser_save_session, browser_goto, browser_click,
+          browser_fill, browser_select, browser_read_text, browser_all_texts, browser_url]
```
Also worth a P1: detect session death early (`browser_load_session` could goto the inventory URL
and report `SESSION_EXPIRED` before the workflow starts).

**P2 — lock down the MCP demo agent.** `mcp_server.demo()` sets only `allowed_tools`, which is
additive: the outer agent kept Bash/Read/Grep and used Bash 14× in the audit run.

```diff
--- a/mcp_server.py
+++ b/mcp_server.py
@@     opts = ClaudeAgentOptions(
         mcp_servers={"saucedemo": server},
         allowed_tools=["mcp__saucedemo__record_workflow", "mcp__saucedemo__replay_workflow"],
+        disallowed_tools=["Bash", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"],
         hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard])]},
```

**P2 — defuse strict-mode fallbacks.** Steps 5/6 fallbacks (`get_by_role("button", name="Add to
cart")`, `get_by_text("Add to cart")`) match 6 buttons; step 7's `get_by_text("2")` is ambiguous
(`locator_resilience.json` baseline). An agent following a fallback literally trips Playwright
strict mode. Render multi-match fallbacks with a `.first` suffix or drop them:

```diff
--- a/recorder.py
+++ b/recorder.py
@@ def pick_locators(d):
@@     if d.get("role") and d.get("name"):
-        out.append(f'get_by_role({_q(d["role"])}, name={_q(d["name"])}, exact=True)')
+        out.append(f'get_by_role({_q(d["role"])}, name={_q(d["name"])}, exact=True)'
+                   + ('.first  # matches multiple; .first avoids strict-mode' if d.get("role") == "button" else ''))
```

**P3 — pin cart *contents*, not just counts.** Wrong-item tampers on the second add-to-cart are
MISSED end-to-end (wrong total returned). Derive one check per cart item from the per-item
testids (`item-N-title-link`) instead of the first 80 chars of the summary container.

**P3 — README install gaps + trace.zip churn.** Add to README: `python3 -m venv .venv`,
`pip install -r requirements.txt`, `playwright install chromium`, and note that
`recordings/saucedemo_checkout/trace.zip` is regenerated (uncommitted-diff-prone) by every
recorder run — best gitignored like `recordings/*/trace/` already is.

---

## Re-running the audit

```bash
tests/acceptance/run_audit.sh                # deterministic phases (~15 min, no model, no replays)
tests/acceptance/run_audit.sh --with-replays # adds the 6-replay sequence (~60-90 min)
```
Phases: preflight+sleep-grep → clean-clone README walkthrough (2 recorder runs + demonstrator
diff) → hook unit suite → skill structure → session/empty-cart → off-site click → network
interception comparison → step-level tampers → locator resilience → (replays R1-R6) →
log reconciliation. Evidence paths cited throughout this report.

## Assumptions & methodology notes

- Replay budget: 6 full agent replays (R1–R6). The SDK restriction/auth probe, recorder runs,
  session refreshes, the step-level tamper harness and the network/offsite harnesses are not
  workflow replays.
- Tampers (a)/(b) were evaluated with a deterministic step-level harness (`test_tamper_steps.py`)
  that executes the skill verbatim and evaluates its checks; the same check mechanism is proven at
  agent level by R5/R6, so step-level results are valid for CAUGHT/MISSED without burning replays.
- The repo's `run_pass_test.py` was **not** executed as-is (it runs 3 replays; budget). Its PASS-1
  and PASS-2 halves were verified individually (R1/R2 and R5 + step-level b).
- `tests/acceptance/test_locator_resilience.py` shipped by the prior audit had test bugs (mixed
  Playwright/JS asserts, pre-sort comparison, missing stage anchors). Fixed in this audit; the
  class-strip/reorder scenarios still cannot self-verify against the live SPA because React
  re-applies classes and re-sorts client-side after hydration — noted, baseline + wrap_body cover
  all 14 steps and pass.
- `recordings/saucedemo_checkout/trace.zip` was already modified vs HEAD pre-audit; it was
  rewritten again by the MCP demo's `record_workflow` (regenerated binary, timing-dependent) and
  restored to HEAD afterwards. `skills/saucedemo_checkout.md` and
  `recordings/saucedemo_checkout/steps.json` are byte-identical to HEAD before and after the audit.
- Model quirk (NOTES.md): the SDK CLI warns `[claude-code:unrecognized_model]` and uses its
  default model; all replay runs share this behavior, so run-to-run comparisons are apples-to-apples.
