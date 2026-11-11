"""PreToolUse hook: log every tool call; block navigation outside saucedemo.com; limit Read to skills/*.md."""
import json
import time
from pathlib import Path
from urllib.parse import urlparse

LOG = Path("logs/tool_calls.jsonl")
SKILLS = Path("skills").resolve()


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _allowed_host(url: str) -> bool:
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host == "saucedemo.com" or host.endswith(".saucedemo.com")


async def log_and_guard(input_data, tool_use_id, context):
    name = input_data.get("tool_name", "")
    inp = input_data.get("tool_input", {})
    LOG.parent.mkdir(exist_ok=True)
    decision = None

    if name.endswith("browser_goto") and not _allowed_host(str(inp.get("url", ""))):
        decision = _deny(f"Blocked: navigation outside saucedemo.com ({inp.get('url')})")
    elif name == "Read":
        p = Path(str(inp.get("file_path", ""))).resolve()
        if not (p.suffix == ".md" and SKILLS in p.parents):
            decision = _deny("Blocked: the agent may only read files in skills/*.md")

    with open(LOG, "a") as f:
        f.write(json.dumps({"t": time.time(), "tool": name, "input": inp,
                            "blocked": decision is not None}) + "\n")
    return decision or {}
