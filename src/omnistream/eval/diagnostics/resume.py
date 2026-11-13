"""Fill only unfinished model cells after provider capacity is restored."""

import asyncio

from omnistream.eval.diagnostics import critical, summarize
from omnistream.eval.diagnostics.run import main as run


async def main():
    await run("answers")
    summarize.main()
    critical.main()
    print(
        "Model cells and coverage summaries updated. Review new results before replacing the budget-cutoff diagnosis report."
    )


if __name__ == "__main__":
    asyncio.run(main())
