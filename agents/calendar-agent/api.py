"""
Calendar Agent API — Google Calendar integration (read-only).

Surfaces today's events, upcoming meetings, and free time blocks.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse

from skills.calendar_fetcher import (
    get_today_events,
    get_upcoming_events,
    get_free_slots,
)

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "global")
AGENT_ID = "calendar"

app = FastAPI(
    title="Nerve Center Calendar Agent",
    version="1.0.0",
    description="Google Calendar agent — surfaces your schedule.",
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


@app.get("/today")
def today(_key: str = Depends(verify_api_key)):
    """Get today's events."""
    events = get_today_events()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"events": events})


@app.get("/upcoming")
def upcoming(
    hours: int = Query(default=48, ge=1, le=168),
    _key: str = Depends(verify_api_key),
):
    """Get upcoming events."""
    events = get_upcoming_events(hours=hours)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"events": events})


@app.get("/free-slots")
def free_slots(
    date: str = Query(default=""),
    _key: str = Depends(verify_api_key),
):
    """Find free time blocks in the day."""
    slots = get_free_slots(date=date or None)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"free_slots": slots})


@app.post("/query")
def query_agent(query: str, _key: str = Depends(verify_api_key)):
    """Handle natural language queries."""
    q = query.lower()
    if "free" in q or "available" in q or "slot" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data={"free_slots": get_free_slots()})
    if "upcoming" in q or "next" in q or "week" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data={"events": get_upcoming_events()})
    # Default: today
    return QueryResponse(status="ok", agent_id=AGENT_ID, data={"events": get_today_events()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
