"""End-to-end check of the local MCP server over streamable HTTP with auth.

Run (server must be running):
    export MCP_AUTH_TOKEN=...        # or: set -a; source ../.env; set +a
    python test_client.py
"""

import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("MCP_URL", "http://127.0.0.1:8765/mcp")
TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")


async def main():
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            tables = await session.call_tool("list_tables", {})
            print("list_tables:", tables.structuredContent or tables.content)

            desc = await session.call_tool("describe_table", {"table": "policies"})
            print("describe policies:", desc.structuredContent or desc.content)

            q = await session.call_tool(
                "query",
                {
                    "sql": (
                        "SELECT policy_type, COUNT(*) AS n, "
                        "ROUND(AVG(premium_monthly),2) AS avg_premium "
                        "FROM policies WHERE status='active' GROUP BY policy_type"
                    )
                },
            )
            print("query:", q.structuredContent or q.content)


if __name__ == "__main__":
    asyncio.run(main())
