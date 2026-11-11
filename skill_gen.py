"""artifacts/steps.json -> skills/saucedemo_checkout.md (the only file the replay agent reads)."""
import json
from pathlib import Path


def generate(src="artifacts/steps.json", out="skills/saucedemo_checkout.md") -> str:
    data = json.loads(Path(src).read_text())
    L = [
        "# Skill: Buy the two cheapest items on saucedemo.com",
        "",
        "## Goal",
        "Log in with the demo user, sort by price (low to high), add the two cheapest items, "
        "check out with made-up details, read the order total from the overview page, "
        "finish, and confirm the thank-you page. Return the order total.",
        "",
        "## Preconditions",
        "- Only https://www.saucedemo.com is allowed. Never navigate anywhere else.",
        "- Demo credentials only (shown on the login page). No real accounts.",
        "- The cart must be empty at the start. A fresh browser session guarantees that.",
        "",
        "## Session",
        "- The recorder saved a logged-in session to `artifacts/state.json`.",
        "- To start from it, call `browser_load_session`, then `browser_goto` to "
        "`https://www.saucedemo.com/inventory.html`, then continue at step 3.",
        "- **A fresh login is needed** (do steps 1-2) if there is no saved session, or if "
        "`/inventory.html` redirects to the login page.",
        "- If you start without a saved session, begin at step 1.",
        "",
        "## Tool guide",
        "- `kind` is one of `test_id`, `role`, `label`, `text`. For `role`, put the role in "
        "`value` and the accessible name in `name`. Pass `name=\"\"` and `nth=0` when unused.",
        "- A locator like \"test id `login-button`\" means `kind=test_id, value=login-button`.",
        "- Tools wait for elements automatically. Never guess a CSS path.",
        "- Check URLs with `browser_url`, text with `browser_read_text`, lists with `browser_all_texts`.",
        "",
        "## Steps",
    ]
    for s in data["steps"]:
        L += [
            f"### Step {s['n']}: {s['title']}",
            f"- **Do:** {s['action']}",
            f"- **Locator:** {s['locator']}",
            f"- **Check:** {s['check']}",
            f"- **If the check fails:** {s['on_fail']}",
            "",
        ]
    L += [
        "## If any step fails",
        "Stop. Reply exactly `FAILED: step N - <what you saw>`. Do not continue and do not guess.",
        "",
        "## Output",
        "Reply with exactly one final line: `ORDER_TOTAL: $xx.xx` (the total from step 7).",
        "",
    ]
    Path(out).parent.mkdir(exist_ok=True)
    Path(out).write_text("\n".join(L))
    return out


if __name__ == "__main__":
    print("wrote", generate())
