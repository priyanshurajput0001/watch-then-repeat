"""Custom MCP tools: record_workflow, replay_workflow. Run `python mcp_server.py` for a demo."""
import asyncio

from claude_agent_sdk import (ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                              AssistantMessage, TextBlock, create_sdk_mcp_server, tool)

from hooks import log_and_guard
from recorder import record
from replayer import DEFAULT_SKILL, replay


def _ok(t):
    return {"content": [{"type": "text", "text": str(t)}]}


@tool("record_workflow", "Record the saucedemo checkout once and generate the skill file.", {})
async def record_workflow(args):
    result = await asyncio.to_thread(record)   # sync Playwright runs in a worker thread
    return _ok(f"recorded; skill file at {result['skill']}; recorded total {result['total']}")


@tool("replay_workflow", "Replay a skill file with the agent. Pass skill_path ('' for default).", {"skill_path": str})
async def replay_workflow(args):
    r = await replay(args.get("skill_path") or DEFAULT_SKILL)
    return _ok(f"total={r['total']} failed_step={r['failed']}")


server = create_sdk_mcp_server(name="saucedemo", version="1.0.0", tools=[record_workflow, replay_workflow])


async def demo():
    opts = ClaudeAgentOptions(
        mcp_servers={"saucedemo": server},
        allowed_tools=["mcp__saucedemo__record_workflow", "mcp__saucedemo__replay_workflow"],
        hooks={"PreToolUse": [HookMatcher(hooks=[log_and_guard])]},
    )
    async with ClaudeSDKClient(options=opts) as c:
        await c.query("Record the workflow, then replay it and tell me the order total.")
        async for m in c.receive_response():
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, TextBlock):
                        print(b.text)


if __name__ == "__main__":
    asyncio.run(demo())
