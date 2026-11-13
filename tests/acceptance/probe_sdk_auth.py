#!/usr/bin/env python
"""QA audit probe: (1) SDK auth sanity (no browser, 1 turn); (2) prove the replayer's
tool allowlist blocks Bash/Write/WebFetch and that a Read of state.json is denied.
This is NOT a workflow replay (no browser, max 2 turns).
Run: .venv/bin/python tests/acceptance/probe_sdk_auth.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              HookMatcher, TextBlock, ToolResultBlock, UserMessage)
from hooks import log_and_guard


async def run(query, **opt):
    opts = ClaudeAgentOptions(system_prompt="You are a terse assistant.",
                              allowed_tools=list(opt.get("allow", [])),
                              disallowed_tools=list(opt.get("disallow", [])),
                              hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard])]},
                              max_turns=opt.get("turns", 2))
    text, results = "", []
    async with ClaudeSDKClient(options=opts) as c:
        await c.query(query)
        async for m in c.receive_response():
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, TextBlock):
                        text += b.text + "\n"
            elif isinstance(m, UserMessage):
                for b in m.content:
                    if isinstance(b, ToolResultBlock):
                        results.append({"tool": getattr(b, "tool_use_id", "?"), "ok": not b.is_error,
                                        "content": str(b.content)[:300]})
    return text, results


async def main():
    # 1) auth sanity
    t, _ = await run("Reply with exactly: AUTH_OK", turns=1)
    print("[probe] auth sanity:", "PASS" if "AUTH_OK" in t else f"FAIL ({t[:200]!r})")

    # 2) tool restrictions exactly as the replayer configures them
    tools = ["Bash", "Write", "WebFetch"]
    dis = ["Bash", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"]
    q = ("Try to run Bash with the command `echo hi`. Then try to Read "
         f"{ROOT}/artifacts/state.json. Then try WebFetch on https://example.com. "
         "For each, report the exact tool_result you got (error text included). Do not try anything else.")
    t, results = await run(q, allow=["Read"], disallow=dis, turns=6)
    print("--- tool_results seen by the model ---")
    for r in results:
        print(f"  ok={r['ok']}  {r['content']!r}")
    print("--- assistant text ---")
    print(t)
    ev = ROOT / "reports/evidence/audit6_probe_restrictions.txt"
    ev.parent.mkdir(parents=True, exist_ok=True)
    with open(ev, "w") as f:
        f.write("tool_results:\n" + "\n".join(repr(r) for r in results) + "\n\nassistant:\n" + t)
    print(f"[probe] evidence -> {ev}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
