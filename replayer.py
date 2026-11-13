"""Agent SDK agent that reads ONLY the skill file, replays the workflow, returns the order total."""
import asyncio
import re
import sys

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              HookMatcher, TextBlock)

from browser_tools import TOOL_NAMES, browser_server, close_browser
from hooks import log_and_guard

DEFAULT_SKILL = "skills/saucedemo_checkout.md"

SYSTEM = (
    "You are a careful browser automation agent. Read the skill file you are given and follow it "
    "exactly, step by step, verifying each step's Check before continuing. Use only the browser tools. "
    "If a check still fails after the skill's retry rule, stop and report the failed step. Never guess."
)


def parse_result(text: str) -> dict:
    """Read the skill's output contract out of the final reply: `ORDER_TOTAL: $X.XX`
    (or a bare `Total: $X.XX`) on success, `FAILED_STEP: <n>` / `FAILED: step <n>` on failure."""
    m = re.findall(r"(?:ORDER_TOTAL|(?<![A-Za-z])Total)\s*:\s*\$(\d+\.\d\d)", text, flags=re.I)
    f = re.findall(r"(?:FAILED_STEP|FAILED)\s*:\s*(?:step\s*)?(\d+)", text, flags=re.I)
    return {"total": float(m[-1]) if m else None, "failed": int(f[-1]) if (f and not m) else None}


async def replay(skill_path: str = DEFAULT_SKILL) -> dict:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        mcp_servers={"browser": browser_server},
        allowed_tools=TOOL_NAMES + ["Read"],
        disallowed_tools=["Bash", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"],
        hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard])]},
        max_turns=60,
    )
    text = ""
    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(f"Read `{skill_path}` and follow it exactly. Return the order total.")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            text += b.text + "\n"
    finally:
        await close_browser()

    return {**parse_result(text), "transcript": text}


if __name__ == "__main__":
    r = asyncio.run(replay(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SKILL))
    print(r["transcript"])
    print("TOTAL:", r["total"], "| FAILED STEP:", r["failed"])
