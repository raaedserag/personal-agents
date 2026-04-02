"""
Slack Agent API — Read-only Slack integration.

Surfaces mentions, DMs, and channel highlights for the morning briefing.
Uses a user token (xoxp-...) for authentication.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse

from skills.slack_fetcher import (
    get_recent_mentions,
    get_channel_updates,
    get_dm_summary,
    get_unread_highlights,
)

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "unknown")
AGENT_ID = f"slack-{PROFILE_ID}"

app = FastAPI(
    title=f"Nerve Center Slack Agent ({PROFILE_ID})",
    version="1.0.0",
    description=f"Slack agent for profile '{PROFILE_ID}'",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "profile": PROFILE_ID,
        "scope": "individual",
        "version": "1.0.0",
    }


@app.get("/mentions")
def mentions(
    hours: int = Query(default=24, ge=1, le=168),
    _key: str = Depends(verify_api_key),
):
    """Get recent mentions."""
    data = get_recent_mentions(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=data)


@app.get("/channels")
def channels(
    hours: int = Query(default=12, ge=1, le=72),
    _key: str = Depends(verify_api_key),
):
    """Get recent channel updates."""
    data = get_channel_updates(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=data)


@app.get("/dms")
def dms(
    hours: int = Query(default=24, ge=1, le=168),
    _key: str = Depends(verify_api_key),
):
    """Get recent DMs."""
    data = get_dm_summary(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=data)


@app.get("/highlights")
def highlights(
    hours: int = Query(default=24, ge=1, le=168),
    _key: str = Depends(verify_api_key),
):
    """Get combined unread highlights — mentions, DMs, channels."""
    data = get_unread_highlights(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=data)


@app.post("/query")
def query_agent(query: str, _key: str = Depends(verify_api_key)):
    """Handle natural language queries."""
    q = query.lower()
    if "mention" in q or "tagged" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_recent_mentions())
    if "dm" in q or "direct" in q or "message" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_dm_summary())
    if "channel" in q or "update" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_channel_updates())
    # Default: highlights
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_unread_highlights())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
