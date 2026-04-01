"""
Blocker Monitor — Periodically checks for blockers across all agents.

Used by the scheduler to generate blocker alerts on a cron schedule.
Also supports on-demand blocker checks via the API.
"""

from __future__ import annotations

from .briefing_builder import (
    get_registry,
    _collect_jira_data,
    _collect_infra_data,
)


def check_blockers() -> dict:
    """Check all agents for blockers and return a structured summary."""
    registry = get_registry()

    jira_data = _collect_jira_data(registry)
    infra_data = _collect_infra_data(registry)

    blockers: list[dict] = []

    # Extract blocked tickets from jira data
    for agent_id, data in jira_data.items():
        profile = agent_id.replace("jira-", "")
        standup = data.get("standup", {})
        if isinstance(standup, dict):
            for t in standup.get("blocked_tickets", []):
                blockers.append({
                    "source": "jira",
                    "profile": profile,
                    "key": t.get("key", "?"),
                    "summary": t.get("summary", "?"),
                    "assignee": t.get("assignee", "?"),
                    "priority": t.get("priority", "?"),
                })

    # Extract infra incidents (if available)
    for agent_id, data in infra_data.items():
        if isinstance(data, dict) and data.get("status") == "ok":
            incidents = data.get("data", {})
            if isinstance(incidents, dict):
                for inc in incidents.get("incidents", []):
                    blockers.append({
                        "source": "infra",
                        "profile": "zeal",
                        "key": inc.get("id", "?"),
                        "summary": inc.get("title", inc.get("summary", "?")),
                        "assignee": inc.get("assigned_to", "?"),
                        "priority": inc.get("severity", "?"),
                    })

    return {
        "total_blockers": len(blockers),
        "blockers": blockers,
        "has_blockers": len(blockers) > 0,
    }
