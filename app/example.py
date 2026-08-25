"""One-shot example: ask StockJarvis a question against the filings DB."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from app.agent import create_agent
from vanna.core.user.request_context import RequestContext

QUESTION = "List five company names and their symbols from the database."


async def run_example() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    agent = create_agent()
    context = RequestContext(cookies={}, metadata={}, remote_addr="127.0.0.1")
    print(f"Q: {QUESTION}\n")
    async for component in agent.send_message(
        request_context=context,
        message=QUESTION,
        conversation_id="example-1",
    ):
        simple = getattr(component, "simple_component", None)
        if simple is not None and getattr(simple, "text", None):
            print(simple.text)
            continue
        rich = getattr(component, "rich_component", None)
        if rich is not None and getattr(rich, "content", None):
            print(rich.content)


def main() -> None:
    asyncio.run(run_example())


if __name__ == "__main__":
    main()
