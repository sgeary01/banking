"""
servicenow-mock — a minimal stand-in for ServiceNow ITSM.

Receives Alertmanager webhooks at /api/now/webhook and turns each alert into an
incident (keyed by Alertmanager fingerprint, auto-resolved when the alert
clears). Exposes the incidents two ways:

  GET /api/now/table/incident   ServiceNow-style Table API ({"result": [...]})
  GET /                         an HTML incident-queue UI for screen sharing

Storage is in-memory — fine for a demo; incidents reset when the pod restarts.
"""

import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import HTMLResponse

from observability import create_app, get_logger

log = get_logger()

# fingerprint → incident dict
_incidents: dict = {}
_counter = {"n": 10000}

# Alertmanager severity → ServiceNow priority / urgency / impact
PRIORITY = {
    "critical": ("1 - Critical", "1 - High", "1 - High"),
    "warning": ("3 - Moderate", "2 - Medium", "2 - Medium"),
}
DEFAULT_PRIORITY = ("4 - Low", "3 - Low", "3 - Low")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@asynccontextmanager
async def lifespan(app):
    log.info("servicenow-mock started")
    yield


app = create_app("ServiceNow Mock", lifespan=lifespan)


# ── Webhook receiver ───────────────────────────────────────────────────────────

@app.post("/api/now/webhook")
async def receive_alerts(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", []) or []
    created, updated, resolved = 0, 0, 0

    for a in alerts:
        fp = a.get("fingerprint")
        if not fp:
            continue
        labels = a.get("labels", {}) or {}
        annotations = a.get("annotations", {}) or {}
        status = (a.get("status") or payload.get("status") or "firing").lower()
        severity = (labels.get("severity") or "").lower()
        ci = labels.get("job") or labels.get("service") or "unknown"
        alertname = labels.get("alertname", "Alert")
        priority, urgency, impact = PRIORITY.get(severity, DEFAULT_PRIORITY)

        existing = _incidents.get(fp)
        if existing is None:
            _counter["n"] += 1
            inc = {
                "number": f"INC{_counter['n']:07d}",
                "sys_id": fp,
                "opened_at": _now(),
                "sys_created_on": _now(),
            }
            _incidents[fp] = inc
        else:
            inc = existing

        inc.update({
            "short_description": f"{alertname}: {annotations.get('summary', ci)}",
            "description": annotations.get("description", ""),
            "cmdb_ci": ci,
            "category": "Software",
            "assignment_group": "Banking SRE",
            "priority": priority,
            "urgency": urgency,
            "impact": impact,
            "severity": severity or "n/a",
            "alertname": alertname,
            "sys_updated_on": _now(),
        })

        if status == "resolved":
            inc["state"] = "6 - Resolved"
            inc["closed_at"] = _now()
            resolved += 1
        elif existing is None:
            inc["state"] = "1 - New"
            created += 1
        else:
            if inc.get("state") != "2 - In Progress":
                inc["state"] = "1 - New"
            updated += 1

    log.info("alertmanager webhook processed", created=created, updated=updated,
             resolved=resolved, total=len(_incidents))
    return {"result": {"created": created, "updated": updated, "resolved": resolved}}


# ── ServiceNow-style Table API ───────────────────────────────────────────────

@app.get("/api/now/table/incident")
async def list_incidents(sysparm_limit: int = 100):
    items = sorted(_incidents.values(), key=lambda i: i["opened_at"], reverse=True)
    return {"result": items[:sysparm_limit]}


# ── Incident-queue UI ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def queue_view():
    items = sorted(_incidents.values(), key=lambda i: i["opened_at"], reverse=True)
    rows = []
    for i in items:
        sev = i.get("severity", "n/a")
        state = i.get("state", "1 - New")
        state_cls = "resolved" if state.endswith("Resolved") else "open"
        rows.append(
            f"<tr class='{state_cls}'>"
            f"<td class='num'>{i['number']}</td>"
            f"<td><span class='pri pri-{sev}'>{i.get('priority','')}</span></td>"
            f"<td>{i.get('short_description','')}</td>"
            f"<td class='ci'>{i.get('cmdb_ci','')}</td>"
            f"<td>{i.get('assignment_group','')}</td>"
            f"<td class='state-{state_cls}'>{state}</td>"
            f"<td class='time'>{i.get('opened_at','')}</td>"
            "</tr>"
        )
    body = "".join(rows) or (
        "<tr><td colspan='7' class='empty'>No incidents yet. Trigger a chaos scenario.</td></tr>"
    )
    open_count = sum(1 for i in items if not i.get("state", "").endswith("Resolved"))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>ServiceNow — Incidents (mock)</title>
<meta http-equiv="refresh" content="10">
<style>
  body {{ font-family:-apple-system,Segoe UI,Roboto,sans-serif; margin:0; background:#f0f2f5; color:#2e2e2e; }}
  .hdr {{ background:#293e40; color:#fff; padding:14px 24px; display:flex; align-items:center; gap:14px; }}
  .hdr .logo {{ font-weight:700; letter-spacing:.5px; }}
  .hdr .badge {{ background:#62d84e; color:#06331a; font-weight:600; border-radius:12px; padding:2px 10px; font-size:13px; }}
  .hdr small {{ opacity:.7; margin-left:auto; font-weight:400; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; }}
  th,td {{ text-align:left; padding:10px 14px; font-size:13px; border-bottom:1px solid #e4e7eb; }}
  th {{ background:#fafbfc; color:#5a6872; text-transform:uppercase; font-size:11px; letter-spacing:.4px; }}
  .num {{ font-family:monospace; color:#1f6fb2; }}
  .ci {{ font-family:monospace; }}
  .pri {{ font-size:11px; padding:1px 8px; border-radius:10px; color:#fff; white-space:nowrap; }}
  .pri-critical {{ background:#c0392b; }} .pri-warning {{ background:#e08e0b; }} .pri-n\\/a {{ background:#888; }}
  .state-resolved {{ color:#3c9a5f; font-weight:600; }} .state-open {{ color:#c0392b; font-weight:600; }}
  tr.resolved {{ opacity:.6; }}
  .time {{ color:#7a7a7a; font-family:monospace; }}
  .empty {{ text-align:center; color:#888; padding:40px; }}
</style></head><body>
<div class="hdr"><span class="logo">ServiceNow</span> &nbsp;›&nbsp; Incident
  <span class="badge">{open_count} open</span>
  <small>mock instance — auto-refresh 10s</small></div>
<table>
  <thead><tr><th>Number</th><th>Priority</th><th>Short description</th>
    <th>Configuration item</th><th>Assignment group</th><th>State</th><th>Opened</th></tr></thead>
  <tbody>{body}</tbody>
</table>
</body></html>"""
