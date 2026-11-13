#!/usr/bin/env python
"""QA audit replay runner. One agent replay of a skill, with per-run accounting:

  - wall duration, ORDER_TOTAL / FAILED step
  - every tool_use block seen in the SDK transcript
  - slice of logs/tool_calls.jsonl written during this run (hook log)
  - reconciliation: transcript tool_use count == hook log line count for this run

Uses the SAME agent wiring as replayer.py (same options; cited at replayer.py:22-29) so
the run is a faithful product replay. Usage:

  .venv/bin/python tests/acceptance/run_replay.py <skill_path> <evidence_prefix>
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              HookMatcher, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage)
from browser_tools import TOOL_NAMES, browser_server, close_browser
from hooks import LOG, log_and_guard
from replayer import SYSTEM  # identical system prompt to the product replayer


async def replay_audited(skill_path: str):
    # Options copied verbatim from replayer.replay() (replayer.py:22-29).
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        mcp_servers={"browser": browser_server},
        allowed_tools=TOOL_NAMES + ["Read"],
        disallowed_tools=["Bash", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"],
        hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard])]},
        max_turns=60,
    )
    tool_uses, tool_results, text = [], [], ""
    t0 = time.time()
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(f"Read `{skill_path}` and follow it exactly. Return the order total.")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            text += b.text + "\n"
                        elif isinstance(b, ToolUseBlock):
                            tool_uses.append({"tool": b.name, "input": b.input})
                elif isinstance(msg, UserMessage):
                    for b in msg.content:
                        if isinstance(b, ToolResultBlock):
                            tool_results.append({"for": b.tool_use_id, "ok": not b.is_error,
                                                 "content": str(b.content)[:400]})
    finally:
        await close_browser()
    duration = time.time() - t0

    import re
    m = re.findall(r"ORDER_TOTAL:\s*(\$\d+\.\d\d)", text)
    f = re.findall(r"FAILED:\s*step\s*(\d+)[^\n]*", text, flags=re.I)
    return {"total": m[-1] if m else None, "failed": f[-1] if (f and not m) else None,
            "text": text, "tool_uses": tool_uses, "tool_results": tool_results, "duration": duration}


async def main():
    skill_path = sys.argv[1]
    prefix = sys.argv[2]
    out_dir = ROOT / "reports/evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = ROOT / LOG
    pre_lines = log_path.read_text().splitlines() if log_path.exists() else []

    r = await replay_audited(skill_path)

    post_lines = log_path.read_text().splitlines() if log_path.exists() else []
    new_log = [json.loads(l) for l in post_lines[len(pre_lines):]]
    log_names = [e["tool"] for e in new_log]
    tran_names = [t["tool"] for t in r["tool_uses"]]
    reconcile = {
        "transcript_tool_uses": len(tran_names),
        "hook_log_lines_this_run": len(new_log),
        "counts_match": len(tran_names) == len(new_log),
        "blocked_in_log": sum(1 for e in new_log if e["blocked"]),
        "log_sequence": log_names,
        "transcript_sequence": tran_names,
        "sequences_match": log_names == tran_names,
    }
    summary = {"skill": skill_path, "prefix": prefix, "total": r["total"], "failed": r["failed"],
               "duration_s": round(r["duration"], 1), "tool_calls": len(tran_names),
               "reconcile": reconcile}
    (out_dir / f"{prefix}.summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / f"{prefix}.transcript.txt").write_text(r["text"])
    (out_dir / f"{prefix}.tool_uses.json").write_text(json.dumps(r["tool_uses"], indent=2))
    (out_dir / f"{prefix}.tool_results.json").write_text(json.dumps(r["tool_results"], indent=2))
    (out_dir / f"{prefix}.hook_log.jsonl").write_text("\n".join(post_lines[len(pre_lines):]) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "reconcile"}, indent=2))
    print("reconcile:", json.dumps({k: v for k, v in reconcile.items() if k not in ("log_sequence", "transcript_sequence")}))


if __name__ == "__main__":
    asyncio.run(main())
