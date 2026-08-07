"""Local MCP server: a read-only front end to mcp-db/data.db (Atlas Financial).

Transport: streamable HTTP at /mcp (works for Claude Code now, and for the
Resolve satellite later). Auth: static bearer token from MCP_AUTH_TOKEN.

Run:
    export MCP_AUTH_TOKEN=...        # or: set -a; source ../.env; set +a
    python server.py                # serves http://127.0.0.1:8765/mcp

Bind host/port via MCP_HOST / MCP_PORT (defaults 127.0.0.1:8765). When the
Resolve satellite needs to reach this from the k3d cluster, set
MCP_HOST=0.0.0.0 so host.k3d.internal:8765 resolves to it.
"""

import os
import re
import secrets
import sqlite3
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

DB_PATH = Path(__file__).parent / "data.db"
AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "8765"))

MAX_ROWS = 1000
# A query must be a single read-only statement. SQLite read-only connection is
# the hard guarantee; this check just gives callers a clean error.
SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

mcp = FastMCP("banking-db")


def _connect() -> sqlite3.Connection:
    """Open data.db strictly read-only (writes fail at the SQLite layer)."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run seed.py first.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


@mcp.tool()
def list_tables() -> list[str]:
    """List all tables in the database."""
    with _connect() as conn:
        return _table_names(conn)


@mcp.tool()
def describe_table(table: str) -> list[dict]:
    """Return column info (name, type, notnull, primary key) for one table."""
    with _connect() as conn:
        if table not in _table_names(conn):
            raise ValueError(f"Unknown table: {table}")
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [
            {
                "name": r["name"],
                "type": r["type"],
                "notnull": bool(r["notnull"]),
                "pk": bool(r["pk"]),
            }
            for r in rows
        ]


@mcp.tool()
def query(sql: str, limit: int = 100) -> dict:
    """Run a read-only SELECT (or WITH ... SELECT) and return columns and rows.

    Only a single read-only statement is allowed. limit caps returned rows
    (default 100, max 1000); it does not modify the SQL.
    """
    if not SELECT_RE.match(sql or ""):
        raise ValueError("Only SELECT / WITH queries are permitted.")
    if ";" in sql.strip().rstrip(";"):
        raise ValueError("Only a single statement is permitted.")
    limit = max(1, min(int(limit), MAX_ROWS))
    with _connect() as conn:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        return {
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) == limit,
        }


class BearerAuth:
    """Pure-ASGI bearer check. Rejects any HTTP request without the token.

    Implemented at the ASGI layer (not BaseHTTPMiddleware) so it never buffers
    the streamable-HTTP response body.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}" if token else ""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"").decode()
        if not self.expected or not secrets.compare_digest(provided, self.expected):
            await JSONResponse({"error": "unauthorized"}, status_code=401)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


def build_app():
    if not AUTH_TOKEN:
        raise SystemExit("MCP_AUTH_TOKEN is not set. Refusing to start without auth.")
    return BearerAuth(mcp.streamable_http_app(), AUTH_TOKEN)


if __name__ == "__main__":
    uvicorn.run(build_app(), host=HOST, port=PORT)
