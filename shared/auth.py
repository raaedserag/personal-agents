"""
Auth — API key verification for inter-agent communication + dashboard PIN.
"""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Header, Depends
from fastapi.security import HTTPBearer


# ── Agent-to-Agent API Key Auth ──────────────────────────────────

def get_agent_api_key() -> str:
    """Get the configured agent API key from environment."""
    return os.getenv("AGENT_API_KEY", "")


def verify_api_key(x_api_key: str = Header(None)) -> str:
    """FastAPI dependency to verify inter-agent API keys.

    Usage:
        @app.get("/tickets/mine")
        def my_tickets(key: str = Depends(verify_api_key)):
            ...
    """
    expected = get_agent_api_key()
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="AGENT_API_KEY not configured on this agent.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )
    return x_api_key


# ── Dashboard PIN Auth ───────────────────────────────────────────

def get_dashboard_pin() -> str:
    """Get the dashboard PIN from environment."""
    return os.getenv("DASHBOARD_PIN", "")


def verify_dashboard_pin(pin: str) -> bool:
    """Verify a dashboard PIN. Returns True if valid."""
    expected = get_dashboard_pin()
    if not expected:
        # No PIN configured — allow access (local-only scenario)
        return True
    return hmac.compare_digest(pin, expected)


# ── Optional Auth (for endpoints that may or may not require auth) ──

def optional_api_key(x_api_key: str = Header(None)) -> str | None:
    """Like verify_api_key but doesn't raise if no key is configured.
    Useful for health endpoints that should work without auth."""
    expected = get_agent_api_key()
    if not expected:
        return None
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
    return x_api_key
