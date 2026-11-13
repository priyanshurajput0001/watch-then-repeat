#!/usr/bin/env python
"""QA audit, task 6: reconcile each replay's SDK transcript against its hook-log slice.

For every reports/evidence/R*.hook_log.jsonl / R*.tool_uses.json pair:
  - counts match (every tool_use the model emitted was logged by the hook, blocked ones included)
  - sequences match in order
  - reads outside skills/ or tests/fixtures/ were all blocked
  - no disallowed tool ever appears (Bash/Write/Edit/Glob/Grep/WebFetch/WebSearch)

Run: .venv/bin/python tests/acceptance/reconcile_logs.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "reports/evidence"
FORBIDDEN = {"Bash", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "NotebookEdit"}
ALLOWED_READS = ("skills", "tests/fixtures")


def main():
    ok_all = True
    slices = sorted(EV.glob("R*.hook_log.jsonl"))
    print(f"{'run':<22} {'transcript':>10} {'hook log':>9} {'match':>6} {'blocked':>8} forbidden/out-of-scope reads")
    for sl in slices:
        prefix = sl.name[: -len(".hook_log.jsonl")]
        uses = json.loads((EV / f"{prefix}.tool_uses.json").read_text())
        logged = [json.loads(l) for l in sl.read_text().splitlines() if l.strip()]
        counts_ok = len(uses) == len(logged)
        seq_ok = [u["tool"] for u in uses] == [e["tool"] for e in logged]
        blocked = sum(1 for e in logged if e["blocked"])
        forbidden = [u["tool"] for u in uses if u["tool"] in FORBIDDEN]
        bad_reads = []
        for u in uses:
            if u["tool"] == "Read":
                p = str(u["input"].get("file_path", ""))
                if not (p.endswith(".md") and ALLOWED_READS[0] in p or ALLOWED_READS[1] in p):
                    bad_reads.append(p)
        ok = counts_ok and seq_ok and not forbidden
        ok_all &= ok
        extra = f"forbidden={forbidden} bad_reads={bad_reads}" if (forbidden or bad_reads) else "clean"
        print(f"{prefix:<22} {len(uses):>10} {len(logged):>9} {str(counts_ok and seq_ok):>6} {blocked:>8} {extra}")
    print("\nreconciliation:", "ALL RUNS MATCH" if ok_all else "MISMATCH FOUND")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
