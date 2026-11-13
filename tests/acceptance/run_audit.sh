#!/usr/bin/env bash
# One-command QA audit for watch-then-repeat.
#
#   tests/acceptance/run_audit.sh                # deterministic phases only (~15 min, no model)
#   tests/acceptance/run_audit.sh --with-replays # also runs the 6 agent replays (~60-90 min)
#
# Deterministic phases: preflight, clean-clone README walkthrough (2 recorder runs +
# demonstrator-change diff), hook unit tests, skill structure, session/state checks,
# off-site click enforcement, network interception comparison, step-level tampers,
# locator resilience.
# Replay phases (--with-replays), in order:
#   R1  mcp_server.py demo            = MCP evidence + pass-run 1 (also re-records)
#   R2  direct replay                 = pass-run 2
#   R3  state.json deleted            = fresh-login path (task 3) + pass-run 3
#   R4  total-tampered skill          = task 4 (session refreshed first)
#   R5  repo tamper (hilo)            = task 10 repo test (session refreshed first)
#   R6  check-tampered skill          = task 10c (session refreshed first)
# All evidence lands in reports/evidence/. Verdicts land in reports/QA_REPORT.md (manual).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
EV="reports/evidence"
PY=.venv/bin/python
mkdir -p "$EV"
FAILURES=0
phase() { echo; echo "==== $* ===="; }

phase "[0] preflight"
$PY -c "import playwright, claude_agent_sdk; print('imports ok')" || FAILURES=$((FAILURES+1))
ls ~/Library/Caches/ms-playwright/chromium-* >/dev/null 2>&1 && echo "chromium present" || { echo "chromium MISSING"; FAILURES=$((FAILURES+1)); }
curl -sS -o /dev/null -w "saucedemo: %{http_code}\n" --max-time 20 https://www.saucedemo.com/
grep -rn "sleep\|wait_for_timeout" --include="*.py" . 2>/dev/null | grep -v ".venv" | grep -v __pycache__ | grep -v tests/acceptance \
  | tee "$EV/audit6_sleep_grep.txt" || echo "no fixed sleeps in product code (evidence: $EV/audit6_sleep_grep.txt)"

phase "[1] clean clone: tracked files only, fresh venv, README walkthrough"
CLONE=/tmp/wtr_qa_audit_clone
rm -rf "$CLONE" && mkdir -p "$CLONE"
git archive HEAD | tar -x -C "$CLONE"
cd "$CLONE"
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/playwright install chromium 2>&1 | tail -1
cp skills/saucedemo_checkout.md /tmp/clone_skill_committed.md
.venv/bin/python recorder.py | tee /tmp/clone_runA.out
cp recordings/saucedemo_checkout/steps.json /tmp/clone_steps_runA.json
cp skills/saucedemo_checkout.md /tmp/clone_skill_runA.md
.venv/bin/python recorder.py >/dev/null
cmp -s /tmp/clone_steps_runA.json recordings/saucedemo_checkout/steps.json && echo "steps.json A==B byte-identical" || { echo "steps.json DIFFERS"; FAILURES=$((FAILURES+1)); }
cmp -s /tmp/clone_skill_runA.md skills/saucedemo_checkout.md && echo "skill.md A==B byte-identical" || { echo "skill.md DIFFERS"; FAILURES=$((FAILURES+1)); }
cmp -s /tmp/clone_skill_runA.md /tmp/clone_skill_committed.md && echo "regenerated == committed (both files)" || { echo "regenerated != COMMITTED"; FAILURES=$((FAILURES+1)); }
# demonstrator change: recorder internals untouched, one action changes
python3 - <<'EOF'
from pathlib import Path
p = Path("recorder.py"); t = p.read_text()
old = "        for i in range(2):\n"
assert t.count(old) == 1
p.write_text(t.replace(old, "        for i in (0, 2):  # AUDIT: changed demonstrator action\n"))
EOF
.venv/bin/python recorder.py >/dev/null
diff /tmp/clone_skill_runA.md skills/saucedemo_checkout.md > "$EV/audit2_demonstrator_change.diff" && echo "demonstrator change NOT reflected (BAD)" || echo "skill changed with demonstrator (evidence: $EV/audit2_demonstrator_change.diff)"
cp /tmp/clone_steps_runA.json /tmp/clone_skill_runA.md "$EV/" 2>/dev/null || true
mkdir -p "$EV/audit2_recorder" && cp /tmp/clone_skill_runA.md "$EV/audit2_recorder/skill_runA.md"
cd "$ROOT"

phase "[2] hook unit tests (URL matrix, Read guard, log shape)"
$PY tests/acceptance/test_hooks_unit.py | tee "$EV/audit5_hooks_unit.out" || FAILURES=$((FAILURES+1))

phase "[3] skill structure"
$PY tests/acceptance/test_skill_structure.py || FAILURES=$((FAILURES+1))

phase "[4] session refresh + logged-in/empty-cart check"
$PY tests/acceptance/refresh_session.py | tee "$EV/audit3_state_check.out" || FAILURES=$((FAILURES+1))

phase "[5] off-site click enforcement"
$PY tests/acceptance/test_offsite_click.py | tee "$EV/audit5_offsite_click.out" || true

phase "[6] network interception vs request listener"
$PY tests/acceptance/test_network_interception.py | tail -8 | tee "$EV/audit8_network.out" || true

phase "[7] step-level tampers (no model)"
for v in pristine a_step6 a_step5 b; do
  $PY tests/acceptance/test_tamper_steps.py "$v" | tail -3 | tee "$EV/audit10_step_level_${v}.out" || true
done

phase "[8] locator resilience (layout rewrites)"
$PY tests/acceptance/test_locator_resilience.py 2>&1 | tee "$EV/locator_resilience.out" | tail -12 || true

if [ "${1:-}" != "--with-replays" ]; then
  echo; echo "Deterministic phases done (FAILURES=$FAILURES)."
  echo "Run with --with-replays to add the 6 agent replays (~60-90 min)."
  exit "$FAILURES"
fi

phase "[9] R1: MCP demo (record_workflow + replay_workflow through MCP)"
ps aux | grep -iE "ms-playwright|headless_shell" | grep -v grep > "$EV/audit7_browsers_before.txt"
L1=$(wc -l < logs/tool_calls.jsonl)
$PY mcp_server.py > "$EV/audit7_mcp_demo.out" 2>"$EV/audit7_mcp_demo.err"
echo "mcp demo exit=$?" | tee -a "$EV/audit7_mcp_meta.txt"
ps aux | grep -iE "ms-playwright|headless_shell" | grep -v grep > "$EV/audit7_browsers_after.txt"
diff "$EV/audit7_browsers_before.txt" "$EV/audit7_browsers_after.txt" && echo "no zombie playwright browsers" || echo "ZOMBIE BROWSERS FOUND"
grep -c "mcp__saucedemo__record_workflow\|mcp__saucedemo__replay_workflow" <(tail -n +"$((L1+1))" logs/tool_calls.jsonl) \
  | xargs -I{} echo "MCP tool calls logged this run: {}" | tee -a "$EV/audit7_mcp_meta.txt"

phase "[10] R2: direct replay (pass run 2)"
$PY tests/acceptance/run_replay.py skills/saucedemo_checkout.md R2_pass_run1 2>&1 | grep -v unrecognized_model | tail -12

phase "[11] R3: fresh login (state.json deleted; task 3 + pass run 3)"
mv artifacts/state.json /tmp/state_backup_audit_R3.json
$PY tests/acceptance/run_replay.py skills/saucedemo_checkout.md R3_fresh_login 2>&1 | grep -v unrecognized_model | tail -12
mv /tmp/state_backup_audit_R3.json artifacts/state.json

phase "[12] R4: hardcoded-total tamper (task 4)"
$PY tests/acceptance/refresh_session.py >/dev/null || { echo "session refresh failed"; exit 1; }
$PY tests/acceptance/make_tamper_fixtures.py >/dev/null
$PY tests/acceptance/run_replay.py tests/fixtures/saucedemo_checkout_total_tampered.md R4_total_tamper 2>&1 | grep -v unrecognized_model | tail -12

phase "[13] R5: repo's own tamper (sort flipped to hilo; task 10)"
$PY tests/acceptance/refresh_session.py >/dev/null || { echo "session refresh failed"; exit 1; }
$PY tests/acceptance/run_replay.py tests/fixtures/saucedemo_checkout_repo_tampered.md R5_repo_tamper 2>&1 | grep -v unrecognized_model | tail -12

phase "[14] R6: altered check, correct action (task 10c)"
$PY tests/acceptance/refresh_session.py >/dev/null || { echo "session refresh failed"; exit 1; }
$PY tests/acceptance/run_replay.py tests/fixtures/saucedemo_checkout_check_tampered.md R6_check_tamper 2>&1 | grep -v unrecognized_model | tail -12

phase "[15] reconciliation (task 6)"
$PY tests/acceptance/reconcile_logs.py || FAILURES=$((FAILURES+1))

echo
echo "AUDIT COMPLETE (FAILURES=$FAILURES). Evidence in $EV/"
exit "$FAILURES"
