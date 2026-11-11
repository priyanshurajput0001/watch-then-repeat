"""Pass test: replay twice (same total?), then replay a tampered skill (does a check catch it?)."""
import asyncio
from pathlib import Path

from replayer import DEFAULT_SKILL, replay

TAMPERED = "tests/fixtures/saucedemo_checkout_tampered.md"


async def main():
    totals = []
    for i in (1, 2):
        r = await replay(DEFAULT_SKILL)
        print(f"run {i}: total={r['total']} failed={r['failed']}")
        totals.append(r["total"])
    print("PASS 1 (same total twice):", totals[0] is not None and totals[0] == totals[1])

    text = Path(DEFAULT_SKILL).read_text()
    bad = text.replace('Select "Price (low to high)" (value `lohi`)',
                       'Select "Price (high to low)" (value `hilo`)')
    assert bad != text, "tamper target not found; check the sort step text in the skill"
    Path(TAMPERED).parent.mkdir(parents=True, exist_ok=True)
    Path(TAMPERED).write_text(bad)
    r = await replay(TAMPERED)
    print(f"tampered: total={r['total']} failed={r['failed']}")
    print("PASS 2 (check caught the change):", r["total"] is None and r["failed"] is not None)


if __name__ == "__main__":
    asyncio.run(main())
