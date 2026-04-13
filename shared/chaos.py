"""
Chaos state store — checked by every service on each request.
The chaos-service writes flags here; all other services read them.

In a real system this would be Redis. For this demo, it's a simple
in-process dict — the chaos-service hits each service's /chaos/config
endpoint to set state, so each process has its own copy of the flags.
"""

import asyncio
import random
from typing import Optional

# Format: { "service-name": { "latency_ms": 500, "error_rate": 0.3 } }
_chaos_state: dict = {}


def get_chaos(service_name: str) -> dict:
    return _chaos_state.get(service_name, {})


def set_chaos(service_name: str, latency_ms: int = 0, error_rate: float = 0.0) -> None:
    _chaos_state[service_name] = {"latency_ms": latency_ms, "error_rate": error_rate}


def clear_chaos(service_name: str) -> None:
    _chaos_state.pop(service_name, None)


def clear_all() -> None:
    _chaos_state.clear()


async def apply_chaos(service_name: str) -> Optional[dict]:
    """
    Call at the top of route handlers that should be chaos-affected.
    Returns an error dict if this request should fail, else None.
    Applies latency if configured.
    """
    state = get_chaos(service_name)
    if not state:
        return None

    if state.get("latency_ms"):
        await asyncio.sleep(state["latency_ms"] / 1000)

    if state.get("error_rate") and random.random() < state["error_rate"]:
        return {"detail": "Service unavailable (chaos-injected)"}

    return None
