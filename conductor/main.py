"""
Conductor — Central orchestrator for Nerve Center.

No LLM of its own. Routes requests to agents, aggregates responses,
runs scheduled jobs, and serves as the API gateway for CLI and dashboard.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, "/app")
from shared.agent_client import AgentClient, AgentRegistry
from shared.auth import verify_dashboard_pin
from shared.models import QueryResponse

load_dotenv()

# ── Config Loading ───────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ── Agent Registry Setup ────────────────────────────────────────

registry = AgentRegistry()


def init_registry(config: dict) -> None:
    """Register all agents from config."""
    api_key = os.getenv("AGENT_API_KEY", "")
    for agent in config.get("agents", []):
        registry.register(
            agent_id=agent["id"],
            base_url=agent["url"],
            api_key=api_key,
        )


# ── App Lifecycle ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    init_registry(config)
    # TODO: Start scheduler (Phase 1 uses manual triggers only)
    yield


app = FastAPI(
    title="Nerve Center Conductor",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Models ───────────────────────────────────────────────

class ConductorQuery(BaseModel):
    query: str
    profile_id: str = ""


class PinAuth(BaseModel):
    pin: str


# ── Dashboard Auth ───────────────────────────────────────────────

@app.post("/auth/verify")
def verify_pin(auth: PinAuth):
    """Verify dashboard PIN."""
    if verify_dashboard_pin(auth.pin):
        return {"status": "ok"}
    raise HTTPException(status_code=401, detail="Invalid PIN.")


# ── Health & Registry ────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "conductor",
        "version": "1.0.0",
        "agents_registered": len(registry.agent_ids),
    }


@app.get("/agents")
def list_agents():
    """List all registered agents with health status."""
    results = {}
    for agent_id in registry.agent_ids:
        client = registry.get(agent_id)
        if client:
            health_data = client.health()
            results[agent_id] = {
                "url": client.base_url,
                "health": health_data,
            }
    return {"agents": results}


@app.get("/agents/{agent_id}/health")
def agent_health(agent_id: str):
    """Check health of a specific agent."""
    client = registry.get(agent_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")
    return client.health()


# ── Routing ──────────────────────────────────────────────────────

def _route_query(query: str, profile_id: str = "") -> dict[str, list[str]]:
    """Simple intent → agent routing. Returns dict of agent_type → agent_ids.

    This is keyword-based, not LLM-based. Fast and reliable.
    """
    q = query.lower()
    targets: dict[str, list[str]] = {}

    # Jira-related queries
    jira_keywords = ["ticket", "jira", "blocked", "sprint", "standup", "stale", "assign", "transition"]
    if any(kw in q for kw in jira_keywords):
        if profile_id:
            jira_id = f"jira-{profile_id}"
            if registry.get(jira_id):
                targets["jira"] = [jira_id]
        else:
            jira_agents = registry.get_by_type("jira")
            if jira_agents:
                targets["jira"] = [aid for aid, _ in jira_agents]

    # GitHub-related queries
    github_keywords = ["pr", "pull request", "review", "ci", "pipeline", "merge", "diff", "github"]
    if any(kw in q for kw in github_keywords):
        if profile_id:
            gh_id = f"github-{profile_id}"
            if registry.get(gh_id):
                targets["github"] = [gh_id]
        else:
            gh_agents = registry.get_by_type("github")
            if gh_agents:
                targets["github"] = [aid for aid, _ in gh_agents]

    # Infra-related queries
    infra_keywords = ["ecs", "infra", "incident", "pagerduty", "alert", "grafana", "elasticsearch", "deploy"]
    if any(kw in q for kw in infra_keywords):
        infra_agents = registry.get_by_type("infra")
        if infra_agents:
            targets["infra"] = [aid for aid, _ in infra_agents]

    # Planner/briefing queries
    planner_keywords = ["briefing", "morning", "eod", "summary", "plan", "today", "schedule"]
    if any(kw in q for kw in planner_keywords):
        planner = registry.get("planner")
        if planner:
            targets["planner"] = ["planner"]

    # Research queries
    research_keywords = ["research", "look up", "find out", "best practice", "how to"]
    if any(kw in q for kw in research_keywords):
        research = registry.get("research")
        if research:
            targets["research"] = ["research"]

    # Fallback: if no match but profile specified, try jira agent for that profile
    if not targets and profile_id:
        jira_id = f"jira-{profile_id}"
        if registry.get(jira_id):
            targets["jira"] = [jira_id]

    return targets


@app.post("/query")
def query(req: ConductorQuery):
    """Route a natural language query to the appropriate agent(s)."""
    targets = _route_query(req.query, req.profile_id)

    if not targets:
        return QueryResponse(
            status="no_match",
            error="No agents matched your query. Available agents: " + ", ".join(registry.agent_ids),
        )

    # Fan out to all matched agents
    results: dict[str, Any] = {}
    for agent_type, agent_ids in targets.items():
        for agent_id in agent_ids:
            client = registry.get(agent_id)
            if client:
                resp = client.query(req.query, req.profile_id)
                results[agent_id] = resp.model_dump()

    return {
        "status": "ok",
        "routed_to": targets,
        "results": results,
    }


# ── Context Switching ────────────────────────────────────────────

@app.get("/context/{profile_id}")
def switch_context(profile_id: str):
    """Load context for a specific job profile.

    Returns all agents associated with this profile and their status.
    """
    profile_agents = registry.get_by_profile(profile_id)
    if not profile_agents:
        raise HTTPException(
            status_code=404,
            detail=f"No agents found for profile '{profile_id}'.",
        )

    context = {
        "profile_id": profile_id,
        "agents": {},
        "loaded_at": datetime.utcnow().isoformat(),
    }

    for agent_id, client in profile_agents:
        health_data = client.health()
        context["agents"][agent_id] = {
            "url": client.base_url,
            "health": health_data.get("status", "unknown"),
        }

    return context


# ── Briefing Endpoints (manual triggers for Phase 1) ─────────────

@app.get("/briefing/{briefing_type}")
def get_briefing(briefing_type: str, profile_id: str = Query(default="")):
    """Manually trigger a briefing.

    In Phase 1, this aggregates raw data from agents.
    In Phase 2+, the planner agent will synthesize this with an LLM.
    """
    if briefing_type == "blockers":
        return _aggregate_blockers(profile_id)
    elif briefing_type == "tickets":
        return _aggregate_tickets(profile_id)
    elif briefing_type == "prs":
        return _aggregate_prs(profile_id)
    elif briefing_type == "morning":
        return _aggregate_morning(profile_id)
    else:
        return QueryResponse(
            status="unsupported",
            error=f"Briefing type '{briefing_type}' not yet implemented. "
                  f"Available: blockers, tickets, prs, morning.",
        )


def _aggregate_blockers(profile_id: str = "") -> dict:
    """Aggregate blocked tickets from all jira agents."""
    all_blockers: dict[str, Any] = {}

    if profile_id:
        agents = [(f"jira-{profile_id}", registry.get(f"jira-{profile_id}"))]
    else:
        agents = registry.get_by_type("jira")

    for agent_id, client in agents:
        if client:
            result = client.get(f"/tickets/blocked")
            all_blockers[agent_id] = result

    return {"status": "ok", "briefing_type": "blockers", "data": all_blockers}


def _aggregate_tickets(profile_id: str = "") -> dict:
    """Aggregate open tickets from all jira agents."""
    all_tickets: dict[str, Any] = {}

    if profile_id:
        agents = [(f"jira-{profile_id}", registry.get(f"jira-{profile_id}"))]
    else:
        agents = registry.get_by_type("jira")

    for agent_id, client in agents:
        if client:
            result = client.get_my_tickets()
            all_tickets[agent_id] = result

    return {"status": "ok", "briefing_type": "tickets", "data": all_tickets}


def _aggregate_prs(profile_id: str = "") -> dict:
    """Aggregate PR digests from all github agents."""
    all_prs: dict[str, Any] = {}

    if profile_id:
        agents = [(f"github-{profile_id}", registry.get(f"github-{profile_id}"))]
    else:
        agents = registry.get_by_type("github")

    for agent_id, client in agents:
        if client:
            result = client.get_pr_digest()
            all_prs[agent_id] = result

    return {"status": "ok", "briefing_type": "prs", "data": all_prs}


def _aggregate_morning(profile_id: str = "") -> dict:
    """Aggregate a morning briefing from all available agents.

    Combines tickets + blockers + PR digest into one report.
    In Phase 2 the planner agent will synthesize this with an LLM.
    """
    sections: dict[str, Any] = {}

    # Tickets from Jira agents
    if profile_id:
        jira_agents = [(f"jira-{profile_id}", registry.get(f"jira-{profile_id}"))]
    else:
        jira_agents = registry.get_by_type("jira")

    jira_data: dict[str, Any] = {}
    for agent_id, client in jira_agents:
        if client:
            jira_data[agent_id] = {
                "standup": client.get_standup_data(),
                "blocked": client.get_blocked_tickets(),
            }
    sections["jira"] = jira_data

    # PRs from GitHub agents
    if profile_id:
        gh_agents = [(f"github-{profile_id}", registry.get(f"github-{profile_id}"))]
    else:
        gh_agents = registry.get_by_type("github")

    gh_data: dict[str, Any] = {}
    for agent_id, client in gh_agents:
        if client:
            gh_data[agent_id] = client.get_pr_digest()
    sections["github"] = gh_data

    # Infra (if available)
    infra_agents = registry.get_by_type("infra")
    if infra_agents:
        infra_data: dict[str, Any] = {}
        for agent_id, client in infra_agents:
            if client:
                infra_data[agent_id] = client.get("/status")
        sections["infra"] = infra_data

    return {
        "status": "ok",
        "briefing_type": "morning",
        "generated_at": datetime.utcnow().isoformat(),
        "data": sections,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
