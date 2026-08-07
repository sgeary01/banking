# mcp-db

A small local MCP server that fronts a standalone SQLite database
(`data.db`, synthetic Atlas Financial data) so you can query it directly.
Separate from the per-service SQLite DBs the banking lab runs.

- Transport: streamable HTTP at `/mcp`
- Auth: static bearer token (`MCP_AUTH_TOKEN`)
- Tools (all read-only): `list_tables`, `describe_table`, `query`

## Data

`customers` -> `policies` -> (`claims`, `payments`). Regenerate anytime with
`seed.py` (fixed random seed, so it reproduces).

## Setup

```bash
cd mcp-db
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py                      # writes data.db
```

## Run (via Makefile, from the repo root)

The lifecycle is wired into the repo Makefile (token is loaded from the
repo-root `.env` automatically):

```bash
make mcp-up        # start (auto-creates venv, auto-seeds if data.db missing)
make mcp-status    # HTTP 401 => up + auth enforced
make mcp-logs      # tail the server log
make mcp-restart   # bounce
make mcp-down      # stop
make mcp-seed      # regenerate data.db
make mcp-db        # open the SQLite shell directly
make lab-up        # cluster (k3d-up) + this server
make lab-down      # stop this server + tear down the cluster
```

Bind for the satellite later: `make mcp-up MCP_HOST=0.0.0.0`.

## Run (manual)

```bash
set -a; source ../.env; set +a      # exports MCP_AUTH_TOKEN
python server.py                    # http://127.0.0.1:8765/mcp
python test_client.py               # end-to-end check (second shell, same env)
```

## Query the DB directly

```bash
sqlite3 mcp-db/data.db ".tables"
sqlite3 -header -column mcp-db/data.db "SELECT * FROM policies LIMIT 5;"
```

The MCP server opens the DB read-only; the `sqlite3` CLI opens it read-write,
so it doubles as the way to edit data outside the MCP path.

## Use from Claude Code

`.mcp.json` at the repo root registers this server as `banking-db` and reads
the token via `${MCP_AUTH_TOKEN}` expansion. Claude Code does NOT read `.env`
on its own, so export the token before launching:

```bash
set -a; source .env; set +a
claude                              # /mcp should show banking-db connected
```

## Later: connect Resolve via the satellite

Not wired yet. When ready, the server must bind `0.0.0.0` (set
`MCP_HOST=0.0.0.0`) so the in-cluster satellite can reach the Mac host at
`host.k3d.internal:8765`, and this block goes in
`helm/banking/resolve-values.yaml` under `integrations:` (token supplied via a
k8s secret, created by bootstrap from `MCP_AUTH_TOKEN`, same pattern as
`resolve-grafana`):

```yaml
mcpIntegration-main:
  type: mcpIntegration
  create: true
  secretName: mcpIntegration-credentials
  connection:
    mcpServerUrl: http://host.k3d.internal:8765/mcp
```
