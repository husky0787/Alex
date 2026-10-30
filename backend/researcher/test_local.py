"""Run the real Researcher locally; this invokes paid model/cloud services."""
import asyncio
import json
from server import run_research_agent


async def test_local():
    result = await run_research_agent()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_local())
