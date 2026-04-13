"""
Shared async HTTP client with OpenTelemetry trace propagation.
Use this in all inter-service calls so trace context flows automatically.
"""

import httpx
from opentelemetry.propagate import inject


def make_client(base_url: str, timeout: float = 10.0) -> httpx.AsyncClient:
    """
    Returns an httpx.AsyncClient pre-configured to:
      - target base_url
      - inject OTEL trace headers on every request
      - timeout after `timeout` seconds
    """
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        event_hooks={"request": [_inject_trace_headers]},
    )


async def _inject_trace_headers(request: httpx.Request) -> None:
    carrier: dict = {}
    inject(carrier)
    for key, value in carrier.items():
        request.headers[key] = value
