"""
msteams-relay — turns Alertmanager webhooks into Microsoft Teams cards.

Receives Alertmanager webhook POSTs at /alerts, renders a Teams MessageCard,
and (when TEAMS_WEBHOOK_URL is set) forwards it to a real Teams Incoming
Webhook / Power Automate URL. Every card is also kept in an in-memory ring
buffer and rendered at GET / as a mock Teams channel, so the demo works with
or without a real Teams tenant.
"""

import os
import sys
sys.path.insert(0, "/app/shared")

from collections import deque
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.responses import HTMLResponse

from observability import create_app, get_logger
from http_client import make_client

log = get_logger()

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
BUFFER_SIZE = 50

# Last N rendered cards — newest first when displayed
_messages: deque = deque(maxlen=BUFFER_SIZE)

# Severity / status → Teams card accent colour (hex, no leading #)
COLORS = {
    "critical": "D7373F",  # red
    "warning": "F2A93B",   # amber
    "resolved": "57A773",  # green
}


@asynccontextmanager
async def lifespan(app):
    if TEAMS_WEBHOOK_URL:
        log.info("msteams-relay started", teams_forwarding="enabled")
    else:
        log.info("msteams-relay started", teams_forwarding="disabled (mock view only)")
    yield


app = create_app("MS Teams Relay", lifespan=lifespan)


# ── Card rendering ───────────────────────────────────────────────────────────

def _card_color(status: str, severity: str) -> str:
    if status == "resolved":
        return COLORS["resolved"]
    return COLORS.get(severity, COLORS["warning"])


def _build_card(payload: dict) -> tuple[dict, dict]:
    """Render an Alertmanager webhook group into a Teams MessageCard + buffer entry."""
    status = (payload.get("status") or "firing").lower()
    alerts = payload.get("alerts", []) or []
    common = payload.get("commonLabels", {}) or {}
    severity = (common.get("severity") or "").lower()
    if not severity and alerts:
        severity = (alerts[0].get("labels", {}).get("severity") or "").lower()

    alertname = common.get("alertname") or (
        alerts[0].get("labels", {}).get("alertname") if alerts else "Alert"
    )

    if status == "resolved":
        prefix, title = "RESOLVED", f"✅ [RESOLVED] {alertname}"
    elif severity == "critical":
        prefix, title = "FIRING", f"\U0001f534 [FIRING] {alertname}"
    else:
        prefix, title = "FIRING", f"⚠️ [FIRING] {alertname}"

    sections = []
    lines = []
    for a in alerts:
        labels = a.get("labels", {}) or {}
        annotations = a.get("annotations", {}) or {}
        svc = labels.get("job") or labels.get("service") or "unknown"
        facts = [
            {"name": "Service", "value": svc},
            {"name": "Severity", "value": labels.get("severity", "n/a")},
            {"name": "Summary", "value": annotations.get("summary", "")},
            {"name": "Description", "value": annotations.get("description", "")},
        ]
        sections.append({
            "activityTitle": f"{labels.get('alertname', alertname)} — {svc}",
            "facts": [f for f in facts if f["value"]],
            "markdown": True,
        })
        lines.append({
            "service": svc,
            "severity": labels.get("severity", "n/a"),
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
        })

    color = _card_color(status, severity)
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "title": title,
        "sections": sections,
    }
    entry = {
        "title": title,
        "status": status,
        "severity": severity or "n/a",
        "color": color,
        "alert_count": len(alerts),
        "lines": lines,
    }
    return card, entry


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/alerts")
async def receive_alerts(request: Request):
    """Alertmanager webhook receiver."""
    payload = await request.json()
    card, entry = _build_card(payload)
    _messages.appendleft(entry)

    log.info("alert received", status=entry["status"], severity=entry["severity"],
             alert_count=entry["alert_count"], title=entry["title"])

    forwarded = False
    if TEAMS_WEBHOOK_URL:
        try:
            async with make_client(TEAMS_WEBHOOK_URL) as client:
                resp = await client.post("", json=card)
                forwarded = resp.status_code < 400
                if not forwarded:
                    log.warning("teams webhook rejected card", status_code=resp.status_code)
        except Exception as e:  # noqa: BLE001 - best effort, demo relay
            log.warning("failed to forward to teams", error=str(e))

    return {"status": "ok", "forwarded": forwarded, "buffered": len(_messages)}


@app.get("/api/messages")
async def list_messages():
    return list(_messages)


@app.get("/", response_class=HTMLResponse)
async def channel_view():
    rows = []
    for m in _messages:
        bar = f"#{m['color']}"
        body = "".join(
            f"<div class='fact'><b>{ln['service']}</b> "
            f"<span class='sev sev-{ln['severity']}'>{ln['severity']}</span><br>"
            f"<span class='sum'>{ln['summary']}</span><br>"
            f"<span class='desc'>{ln['description']}</span></div>"
            for ln in m["lines"]
        )
        rows.append(
            f"<div class='card' style='border-left:5px solid {bar}'>"
            f"<div class='title'>{m['title']}</div>{body}</div>"
        )
    cards_html = "".join(rows) or "<p class='empty'>No alerts yet. Trigger a chaos scenario.</p>"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Teams — #atlas-app-alerts (mock)</title>
<meta http-equiv="refresh" content="10">
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#f3f2f1; margin:0; }}
  .hdr {{ background:#5b5fc7; color:#fff; padding:14px 24px; font-weight:600; font-size:18px; }}
  .hdr small {{ font-weight:400; opacity:.8; }}
  .feed {{ max-width:760px; margin:24px auto; padding:0 16px; }}
  .card {{ background:#fff; border-radius:8px; padding:14px 16px; margin-bottom:12px;
           box-shadow:0 1px 2px rgba(0,0,0,.08); }}
  .title {{ font-weight:600; font-size:15px; margin-bottom:8px; }}
  .fact {{ font-size:13px; color:#333; margin:6px 0; padding-top:6px; border-top:1px solid #eee; }}
  .sev {{ font-size:11px; padding:1px 6px; border-radius:10px; color:#fff; }}
  .sev-critical {{ background:#d7373f; }} .sev-warning {{ background:#f2a93b; }}
  .sum {{ color:#222; }} .desc {{ color:#666; }}
  .empty {{ color:#888; text-align:center; margin-top:40px; }}
</style></head><body>
<div class="hdr">Microsoft Teams &nbsp;›&nbsp; Atlas Financial SRE &nbsp;›&nbsp; #atlas-app-alerts
  <small>(mock channel — auto-refresh 10s)</small></div>
<div class="feed">{cards_html}</div>
</body></html>"""
