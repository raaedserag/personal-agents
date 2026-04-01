"""
Briefing Builder — Aggregates data from other agents and synthesizes reports.

This is the core skill of the planner agent. It calls jira-agents and github-agents
via HTTP, collects their data, and uses Claude to produce polished briefings.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from shared.agent_client import AgentClient, AgentRegistry
from shared.llm_client import get_llm_client

AGENT_API_KEY = os.getenv("AGENT_API_KEY", "")

# ── Agent discovery ─────────────────────────────────────────────

_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """Get or build the agent registry from environment config."""
    global _registry
    if _registry is not None:
        return _registry

    _registry = AgentRegistry()

    # Read agent URLs from environment (set in docker-compose)
    agent_defs = os.getenv("PLANNER_AGENTS", "")
    if agent_defs:
        # Format: "jira-yassir=http://jira-yassir:8000,github-yassir=http://github-yassir:8000"
        for entry in agent_defs.split(","):
            entry = entry.strip()
            if "=" in entry:
                agent_id, url = entry.split("=", 1)
                _registry.register(agent_id.strip(), url.strip(), AGENT_API_KEY)

    return _registry


# ── Data Collection ─────────────────────────────────────────────

def _collect_jira_data(registry: AgentRegistry) -> dict:
    """Collect standup and blocker data from all jira agents."""
    data: dict = {}
    jira_agents = registry.get_by_type("jira")
    for agent_id, client in jira_agents:
        agent_data: dict = {}
        standup = client.get_standup_data()
        if standup.get("status") == "ok":
            agent_data["standup"] = standup.get("data", {})
        else:
            agent_data["standup"] = {"error": standup.get("error", "Failed to fetch")}

        blocked = client.get_blocked_tickets()
        if blocked.get("status") == "ok":
            agent_data["blocked"] = blocked.get("data", "")
        else:
            agent_data["blocked"] = {"error": blocked.get("error", "Failed to fetch")}

        data[agent_id] = agent_data
    return data


def _collect_github_data(registry: AgentRegistry) -> dict:
    """Collect PR digest data from all github agents."""
    data: dict = {}
    gh_agents = registry.get_by_type("github")
    for agent_id, client in gh_agents:
        digest = client.get_pr_digest()
        if digest.get("status") == "ok":
            data[agent_id] = digest.get("data", {})
        else:
            data[agent_id] = {"error": digest.get("error", "Failed to fetch")}
    return data


def _collect_infra_data(registry: AgentRegistry) -> dict:
    """Collect infra status from infra agents (if available)."""
    data: dict = {}
    infra_agents = registry.get_by_type("infra")
    for agent_id, client in infra_agents:
        status = client.get("/status")
        data[agent_id] = status
    return data


# ── Briefing Synthesis ──────────────────────────────────────────

MORNING_SYSTEM_PROMPT = """You generate morning briefings from raw agent data. Output valid markdown.

Use these sections (skip empty ones):

## Blockers & Incidents
- List each blocker as: **[TICKET-KEY]** Summary — assigned to: Name (Priority)

## Your Tickets Today
- List each ticket as: **[TICKET-KEY]** Summary — Status, Priority
- Group by job profile if multiple profiles have data

## Infra Health
- Brief bullet points about infrastructure status

## PRs Needing Attention
- List each PR as: **repo#number** Title — by Author (CI: status)

## Suggested Focus Order
1. Most urgent items first (blockers, then high priority, then reviews)

Rules:
- Use bullet lists, NOT tables
- Be concise, no filler
- Use the actual data provided, never fabricate IDs
- Bold the ticket keys and PR numbers for readability"""


EOD_SYSTEM_PROMPT = """You generate end-of-day summaries from raw agent data. Output valid markdown.

Use these sections (skip empty ones):

## Still In Progress
- List tickets still being worked on as bullet points

## Blockers Carried Over
- Any blockers that weren't resolved

## PRs Status
- Open PRs, pending reviews

## Tomorrow's Priorities
1. Top 2-3 items to focus on next

Rules:
- Use bullet lists, NOT tables
- Be brief and actionable
- Never fabricate data"""


BLOCKER_SYSTEM_PROMPT = """List blockers from the raw data. Output valid markdown.

Format each as:
- **[TICKET-KEY]** Description — Assignee (Priority)

If there are no blockers, say "No active blockers." only.
Be extremely concise."""


def build_morning_briefing() -> dict:
    """Build a full morning briefing by collecting data from all agents and synthesizing with Claude."""
    registry = get_registry()
    now = datetime.now(timezone.utc)

    # Collect raw data from all agents
    jira_data = _collect_jira_data(registry)
    github_data = _collect_github_data(registry)
    infra_data = _collect_infra_data(registry)

    # Build context for Claude
    raw_context = _format_raw_context(jira_data, github_data, infra_data)

    # Synthesize with Claude
    client = get_llm_client()
    markdown = client.complete(
        messages=[{"role": "user", "content": f"Generate a morning briefing for {now.strftime('%A, %B %d')}.\n\nRaw data:\n{raw_context}"}],
        task_type="heavy",
        system_prompt=MORNING_SYSTEM_PROMPT,
        max_tokens=2048,
    )

    return {
        "briefing_type": "morning",
        "generated_at": now.isoformat(),
        "markdown": markdown,
        "raw_data": {
            "jira": jira_data,
            "github": github_data,
            "infra": infra_data,
        },
    }


def build_eod_summary() -> dict:
    """Build an end-of-day summary."""
    registry = get_registry()
    now = datetime.now(timezone.utc)

    jira_data = _collect_jira_data(registry)
    github_data = _collect_github_data(registry)

    raw_context = _format_raw_context(jira_data, github_data, {})

    client = get_llm_client()
    markdown = client.complete(
        messages=[{"role": "user", "content": f"Generate an end-of-day summary for {now.strftime('%A, %B %d')}.\n\nRaw data:\n{raw_context}"}],
        task_type="heavy",
        system_prompt=EOD_SYSTEM_PROMPT,
        max_tokens=2048,
    )

    return {
        "briefing_type": "eod",
        "generated_at": now.isoformat(),
        "markdown": markdown,
        "raw_data": {
            "jira": jira_data,
            "github": github_data,
        },
    }


def build_blocker_alert() -> dict:
    """Build a focused blocker alert."""
    registry = get_registry()
    now = datetime.now(timezone.utc)

    jira_data = _collect_jira_data(registry)
    infra_data = _collect_infra_data(registry)

    # Extract just blocker-relevant data
    blocker_context_parts: list[str] = []
    for agent_id, data in jira_data.items():
        profile = agent_id.replace("jira-", "")
        blocked = data.get("blocked", "")
        standup = data.get("standup", {})
        blocked_tickets = standup.get("blocked_tickets", []) if isinstance(standup, dict) else []

        blocker_context_parts.append(f"### {profile.upper()}")
        if blocked_tickets:
            for t in blocked_tickets:
                blocker_context_parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} — assigned: {t.get('assignee', '?')}, priority: {t.get('priority', '?')}")
        elif isinstance(blocked, str) and blocked:
            blocker_context_parts.append(blocked)
        else:
            blocker_context_parts.append("No blocked tickets.")

    if infra_data:
        blocker_context_parts.append("\n### INFRA")
        for agent_id, data in infra_data.items():
            blocker_context_parts.append(str(data))

    blocker_context = "\n".join(blocker_context_parts)

    client = get_llm_client()
    markdown = client.complete(
        messages=[{"role": "user", "content": f"Generate a blocker alert.\n\nRaw data:\n{blocker_context}"}],
        task_type="heavy",
        system_prompt=BLOCKER_SYSTEM_PROMPT,
        max_tokens=1024,
    )

    return {
        "briefing_type": "blockers",
        "generated_at": now.isoformat(),
        "markdown": markdown,
    }


def build_pr_digest() -> dict:
    """Build a focused PR digest."""
    registry = get_registry()
    now = datetime.now(timezone.utc)

    github_data = _collect_github_data(registry)

    pr_parts: list[str] = []
    for agent_id, data in github_data.items():
        profile = agent_id.replace("github-", "")
        pr_parts.append(f"### {profile.upper()}")

        if isinstance(data, dict) and "error" not in data:
            my_prs = data.get("my_prs", [])
            review_req = data.get("review_requested", [])
            stale = data.get("stale_prs", [])
            total = len(data.get("open_prs", []))

            pr_parts.append(f"Total open PRs: {total}")

            if my_prs:
                pr_parts.append(f"\nYour PRs ({len(my_prs)}):")
                for pr in my_prs:
                    pr_parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} (CI: {pr.get('ci_status', '?')})")

            if review_req:
                pr_parts.append(f"\nReview Requested ({len(review_req)}):")
                for pr in review_req:
                    pr_parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} by {pr.get('author', '?')}")

            if stale:
                pr_parts.append(f"\nStale PRs ({len(stale)}):")
                for pr in stale:
                    pr_parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} — last update: {pr.get('updated_at', '?')[:10]}")
        else:
            pr_parts.append(f"Error: {data.get('error', 'unknown')}" if isinstance(data, dict) else str(data))

    return {
        "briefing_type": "prs",
        "generated_at": now.isoformat(),
        "markdown": "\n".join(pr_parts),
        "raw_data": {"github": github_data},
    }


# ── Formatting Helpers ──────────────────────────────────────────

def _format_raw_context(jira_data: dict, github_data: dict, infra_data: dict) -> str:
    """Format collected raw data into a text context for Claude."""
    parts: list[str] = []

    # Jira section
    parts.append("## JIRA DATA")
    for agent_id, data in jira_data.items():
        profile = agent_id.replace("jira-", "")
        parts.append(f"\n### {profile.upper()}")

        standup = data.get("standup", {})
        if isinstance(standup, dict) and "error" not in standup:
            my_tickets = standup.get("my_tickets", [])
            if my_tickets:
                parts.append(f"\nOpen tickets ({len(my_tickets)}):")
                for t in my_tickets:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Status: {t.get('status', '?')} | Priority: {t.get('priority', '?')} | Assignee: {t.get('assignee', '?')}")

            blocked = standup.get("blocked_tickets", [])
            if blocked:
                parts.append(f"\nBlocked tickets ({len(blocked)}):")
                for t in blocked:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Assignee: {t.get('assignee', '?')} | Priority: {t.get('priority', '?')}")

            stale = standup.get("stale_tickets", [])
            if stale:
                parts.append(f"\nStale tickets ({len(stale)}):")
                for t in stale:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Assignee: {t.get('assignee', '?')} | Last updated: {t.get('updated', '?')}")
        else:
            parts.append(f"Error fetching standup: {standup}")

    # GitHub section
    parts.append("\n\n## GITHUB DATA")
    for agent_id, data in github_data.items():
        profile = agent_id.replace("github-", "")
        parts.append(f"\n### {profile.upper()}")

        if isinstance(data, dict) and "error" not in data:
            my_prs = data.get("my_prs", [])
            review_req = data.get("review_requested", [])
            stale = data.get("stale_prs", [])

            if my_prs:
                parts.append(f"\nYour open PRs ({len(my_prs)}):")
                for pr in my_prs:
                    parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} | CI: {pr.get('ci_status', '?')} | Reviewers: {', '.join(pr.get('reviewers', [])) or 'none'}")

            if review_req:
                parts.append(f"\nPRs awaiting your review ({len(review_req)}):")
                for pr in review_req:
                    parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} by {pr.get('author', '?')} | Updated: {pr.get('updated_at', '?')[:10]}")

            if stale:
                parts.append(f"\nStale PRs ({len(stale)}):")
                for pr in stale:
                    parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} | Last update: {pr.get('updated_at', '?')[:10]}")

            all_prs = data.get("open_prs", [])
            if all_prs and not my_prs and not review_req:
                parts.append(f"\nAll open PRs ({len(all_prs)}):")
                for pr in all_prs[:10]:
                    parts.append(f"- [{pr.get('repo', '')}#{pr.get('number', '')}] {pr.get('title', '')} by {pr.get('author', '?')}")
        else:
            parts.append(f"Error: {data}")

    # Infra section
    if infra_data:
        parts.append("\n\n## INFRA DATA")
        for agent_id, data in infra_data.items():
            parts.append(f"\n### {agent_id}")
            parts.append(str(data))

    return "\n".join(parts)
