"""
Planner Agent API — FastAPI endpoints.

The "daily brain" — aggregates data from all other agents and produces
synthesized briefings, blocker alerts, and PR digests using Claude.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse

from skills.briefing_builder import (
    build_morning_briefing,
    build_eod_summary,
    build_blocker_alert,
    build_pr_digest,
)
from skills.blocker_monitor import check_blockers

load_dotenv()

AGENT_ID = "planner"

app = FastAPI(
    title="Nerve Center Planner Agent",
    version="1.0.0",
    description="Cross-job planner agent — your daily brain for aggregated briefings.",
)


# ── Health ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "profile": "global",
        "scope": "global",
        "version": "1.0.0",
    }


# ── Briefing Endpoints ──────────────────────────────────────────

@app.get("/briefing/morning")
def morning_briefing(_key: str = Depends(verify_api_key)):
    """Generate a full morning briefing with Claude synthesis."""
    result = build_morning_briefing()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/briefing/eod")
def eod_summary(_key: str = Depends(verify_api_key)):
    """Generate an end-of-day summary with Claude synthesis."""
    result = build_eod_summary()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/briefing/blockers")
def blocker_alert(_key: str = Depends(verify_api_key)):
    """Generate a focused blocker alert with Claude synthesis."""
    result = build_blocker_alert()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/briefing/prs")
def pr_digest(_key: str = Depends(verify_api_key)):
    """Generate a PR digest across all github agents."""
    result = build_pr_digest()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Blocker Check (structured, no LLM) ─────────────────────────

@app.get("/blockers/check")
def blockers_check(_key: str = Depends(verify_api_key)):
    """Quick structured blocker check — no LLM, just data."""
    result = check_blockers()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Query (natural language, for conductor routing) ──────────────

@app.post("/query")
def query_agent(
    query: str,
    profile_id: str = "",
    _key: str = Depends(verify_api_key),
):
    """Handle natural language queries routed from conductor."""
    q = query.lower()

    if "morning" in q or "briefing" in q or "today" in q:
        result = build_morning_briefing()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "eod" in q or "end of day" in q or "summary" in q:
        result = build_eod_summary()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "blocker" in q or "blocked" in q:
        result = build_blocker_alert()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "pr" in q or "pull request" in q or "review" in q:
        result = build_pr_digest()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "plan" in q or "schedule" in q:
        result = build_morning_briefing()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    return QueryResponse(
        status="unsupported", agent_id=AGENT_ID,
        error="Query not understood. Try: 'morning briefing', 'eod summary', 'blocker alert', 'pr digest'.",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
