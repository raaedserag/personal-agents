"""
Jira Agent API — FastAPI endpoints.

Scope-aware: reads PROFILE_SCOPE env var to determine behavior.
- "individual": focuses on user's own tickets
- "leader": adds team-wide endpoints (stale tickets, team standup)
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query
from pydantic import BaseModel

# Add shared package to path
sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse, StandupData, TicketSummary, ProfileScope

from skills import TOOL_REGISTRY
from skills.jira_fetcher import (
    get_my_open_tickets,
    get_my_open_tickets_structured,
    get_ticket_details,
    get_blocked_tickets,
    get_blocked_tickets_structured,
    get_stale_tickets,
    get_recent_activity,
    get_mentioned_tickets,
    search_tickets,
    get_team_open_tickets,
    transition_ticket,
    add_comment,
    assign_ticket,
    create_ticket,
)

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "unknown")
PROFILE_SCOPE = os.getenv("PROFILE_SCOPE", "individual")
AGENT_ID = f"jira-{PROFILE_ID}"

app = FastAPI(
    title=f"Nerve Center Jira Agent ({PROFILE_ID})",
    version="2.0.0",
    description=f"Jira agent for profile '{PROFILE_ID}' (scope: {PROFILE_SCOPE})",
)


# ── Health ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "profile": PROFILE_ID,
        "scope": PROFILE_SCOPE,
        "version": "2.0.0",
    }


# ── Read Endpoints ───────────────────────────────────────────────

@app.get("/tickets/mine")
def my_tickets(
    max_results: int = Query(default=10, ge=1, le=50),
    _key: str = Depends(verify_api_key),
):
    result = get_my_open_tickets(str(max_results))
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/tickets/blocked")
def blocked_tickets(
    project_key: str = Query(default=""),
    _key: str = Depends(verify_api_key),
):
    result = get_blocked_tickets(project_key)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/tickets/{issue_key}")
def ticket_details(
    issue_key: str,
    _key: str = Depends(verify_api_key),
):
    result = get_ticket_details(issue_key)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/tickets/team")
def team_tickets(
    project_key: str = Query(...),
    stale_days: int = Query(default=0, ge=0),
    max_results: int = Query(default=20, ge=1, le=100),
    _key: str = Depends(verify_api_key),
):
    """Get team tickets for a project. If stale_days > 0, returns stale tickets only."""
    if stale_days > 0:
        stale = get_stale_tickets(stale_days, project_key)
        return QueryResponse(
            status="ok", agent_id=AGENT_ID,
            data={"stale_tickets": stale, "stale_days": stale_days},
        )
    result = get_team_open_tickets(project_key, str(max_results))
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Standup Data (structured, for planner agent) ─────────────────

@app.get("/standup-data")
def standup_data(_key: str = Depends(verify_api_key)):
    """Export structured standup data for the planner agent."""
    scope = ProfileScope.LEADER if PROFILE_SCOPE == "leader" else ProfileScope.INDIVIDUAL

    my_tickets = get_my_open_tickets_structured(20)
    # Individual scope: only YOUR blocked tickets. Leader scope: all team blockers.
    blocked = get_blocked_tickets_structured(my_only=(scope == ProfileScope.INDIVIDUAL))

    standup = StandupData(
        profile_id=PROFILE_ID,
        scope=scope,
        my_tickets=[TicketSummary(**t) for t in my_tickets],
        blocked_tickets=[TicketSummary(**t) for t in blocked],
    )

    # Leader scope: also include stale tickets
    if scope == ProfileScope.LEADER:
        stale = get_stale_tickets(days=3)
        standup.stale_tickets = [TicketSummary(**t) for t in stale]

    # Include recent activity as part of standup context
    activity = get_recent_activity(hours=24, max_results=10)

    standup_dict = standup.model_dump()
    standup_dict["recent_activity"] = activity

    return QueryResponse(
        status="ok", agent_id=AGENT_ID,
        data=standup_dict,
    )


# ── Notifications / Activity Feed ───────────────────────────────

@app.get("/notifications")
def notifications(
    hours: int = Query(default=24, ge=1, le=168),
    max_results: int = Query(default=15, ge=1, le=50),
    _key: str = Depends(verify_api_key),
):
    """Get recent activity in configured projects (tickets updated by others)."""
    activity = get_recent_activity(hours=hours, max_results=max_results)
    mentioned = get_mentioned_tickets(days=7, max_results=5)
    return QueryResponse(
        status="ok", agent_id=AGENT_ID,
        data={
            "recent_activity": activity,
            "mentioned": mentioned,
        },
    )


# ── Write Endpoints ──────────────────────────────────────────────

class TransitionRequest(BaseModel):
    issue_key: str
    target_status: str

class CommentRequest(BaseModel):
    issue_key: str
    comment_body: str

class AssignRequest(BaseModel):
    issue_key: str
    assignee_email: str

class CreateRequest(BaseModel):
    project_key: str
    summary: str
    description: str = ""
    issue_type: str = "Task"


@app.post("/tickets/transition")
def do_transition(req: TransitionRequest, _key: str = Depends(verify_api_key)):
    """Transition a ticket to a new status."""
    result = transition_ticket(req.issue_key, req.target_status)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.post("/tickets/comment")
def do_comment(req: CommentRequest, _key: str = Depends(verify_api_key)):
    """Add a comment to a ticket."""
    result = add_comment(req.issue_key, req.comment_body)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.post("/tickets/assign")
def do_assign(req: AssignRequest, _key: str = Depends(verify_api_key)):
    """Assign a ticket to a user."""
    result = assign_ticket(req.issue_key, req.assignee_email)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.post("/tickets/create")
def do_create(req: CreateRequest, _key: str = Depends(verify_api_key)):
    """Create a new ticket."""
    result = create_ticket(req.project_key, req.summary, req.description, req.issue_type)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Query (natural language, for conductor routing) ──────────────

@app.post("/query")
def query_agent(
    query: str,
    project_key: str = "",
    _key: str = Depends(verify_api_key),
):
    """Handle natural language queries routed from conductor."""
    q = query.lower()

    if "my open tickets" in q or "my tickets" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_my_open_tickets())

    if "blocked" in q:
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=get_blocked_tickets(project_key))

    if "search" in q or "find" in q:
        search_text = q.replace("search", "").replace("find", "").strip()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=search_tickets(search_text, project_key))

    if "standup" in q:
        return standup_data(_key)

    if "stale" in q and PROFILE_SCOPE == "leader":
        stale = get_stale_tickets(days=3, project_key=project_key)
        return QueryResponse(status="ok", agent_id=AGENT_ID, data={"stale_tickets": stale})

    return QueryResponse(
        status="unsupported", agent_id=AGENT_ID,
        error="Query not understood. Try: 'my tickets', 'blocked tickets', 'search <query>', 'standup data'.",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
