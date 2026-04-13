import os
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from observability import create_app, get_logger

log = get_logger()

# Downstream service URLs
SERVICES = {
    "auth":         os.getenv("AUTH_SERVICE_URL",         "http://auth-service:8001"),
    "customers":    os.getenv("CUSTOMER_SERVICE_URL",     "http://customer-service:8002"),
    "accounts":     os.getenv("ACCOUNT_SERVICE_URL",      "http://account-service:8003"),
    "transactions": os.getenv("TRANSACTION_SERVICE_URL",  "http://transaction-service:8004"),
    "ledger":       os.getenv("LEDGER_SERVICE_URL",       "http://ledger-service:8005"),
    "fraud":        os.getenv("FRAUD_SERVICE_URL",        "http://fraud-service:8006"),
    "notifications":os.getenv("NOTIFICATION_SERVICE_URL","http://notification-service:8007"),
    "reports":      os.getenv("REPORTING_SERVICE_URL",    "http://reporting-service:8008"),
    "chaos":        os.getenv("CHAOS_SERVICE_URL",        "http://chaos-service:8009"),
}

# Route prefix → service key
ROUTES = [
    ("/auth",           "auth"),
    ("/customers",      "customers"),
    ("/accounts",       "accounts"),
    ("/transactions",   "transactions"),
    ("/ledger",         "ledger"),
    ("/fraud",          "fraud"),
    ("/notifications",  "notifications"),
    ("/reports",        "reports"),
    ("/chaos",          "chaos"),
]


@asynccontextmanager
async def lifespan(app):
    log.info("api-gateway started", services=list(SERVICES.keys()))
    yield

app = create_app("API Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_service(path: str) -> tuple[str, str] | None:
    """Return (base_url, downstream_path) for a given request path."""
    for prefix, svc_key in ROUTES:
        if path.startswith(prefix):
            return SERVICES[svc_key], path
    return None


async def _proxy(request: Request, target_url: str) -> Response:
    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params),
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway(path: str, request: Request):
    full_path = f"/{path}"
    resolved = _resolve_service(full_path)

    if not resolved:
        raise HTTPException(status_code=404, detail=f"No route for /{path}")

    base_url, downstream_path = resolved
    target = f"{base_url}{downstream_path}"

    log.info("proxying request", method=request.method, path=full_path, target=target)

    try:
        return await _proxy(request, target)
    except httpx.ConnectError:
        log.error("upstream connection failed", target=target)
        raise HTTPException(status_code=503, detail=f"Service unavailable: {target}")
    except httpx.TimeoutException:
        log.error("upstream timeout", target=target)
        raise HTTPException(status_code=504, detail="Gateway timeout")
