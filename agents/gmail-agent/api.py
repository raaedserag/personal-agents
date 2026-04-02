"""
Gmail Agent API — Read-only Gmail integration.

Surfaces unread important emails and threads needing action.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse

from skills.gmail_fetcher import (
    get_unread_important,
    get_recent_threads,
    get_action_needed,
)

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "global")
AGENT_ID = "gmail"

app = FastAPI(
    title="Nerve Center Gmail Agent",
    version="1.0.0",
    description="Gmail agent — surfaces emails that need your attention.",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "profile": PROFILE_ID,
        "scope": "global",
        "version": "1.0.0",
    }


@app.get("/unread")
def unread(
    max_results: int = Query(default=10, ge=1, le=50),
    _key: str = Depends(verify_api_key),
):
    """Get unread important emails."""
    emails = get_unread_important(max_results=max_results)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"emails": emails})


@app.get("/recent")
def recent(
    hours: int = Query(default=24, ge=1, le=168),
    _key: str = Depends(verify_api_key),
):
    """Get recently active threads."""
    threads = get_recent_threads(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"threads": threads})


@app.get("/action-needed")
def action_needed(_key: str = Depends(verify_api_key)):
    """Get emails that likely need a reply."""
    emails = get_action_needed()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"emails": emails})


@app.post("/query")
def query_agent(query: str, _key: str = Depends(verify_api_key)):
    """Handle natural language queries."""
    q = query.lower()
    if "action" in q or "reply" in q or "respond" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data={"emails": get_action_needed()})
    if "recent" in q or "thread" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data={"threads": get_recent_threads()})
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"emails": get_unread_important()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
