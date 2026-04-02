"""
Briefing Builder — Aggregates data from other agents and synthesizes reports.

This is the core skill of the planner agent. It calls jira-agents and github-agents
via HTTP, collects their data, and uses the LLM to produce action-oriented briefings.

The briefings answer "What should I do next?" — not just "Here's a data dump."
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
    """Collect standup, blocker, and notification data from all jira agents."""
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

        # Notifications — recent activity by others in your projects
        notifs = client.get_notifications(hours=24)
        if notifs.get("status") == "ok":
            agent_data["notifications"] = notifs.get("data", {})
        else:
            agent_data["notifications"] = {"error": notifs.get("error", "Failed to fetch")}

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


def _collect_slack_data(registry: AgentRegistry) -> dict:
    """Collect Slack highlights from all slack agents."""
    data: dict = {}
    slack_agents = registry.get_by_type("slack")
    for agent_id, client in slack_agents:
        result = client.get_slack_highlights(hours=24)
        if result.get("status") == "ok":
            data[agent_id] = result.get("data", {})
        else:
            data[agent_id] = {"error": result.get("error", "Failed to fetch")}
    return data


def _collect_calendar_data(registry: AgentRegistry) -> dict:
    """Collect today's calendar events."""
    cal = registry.get("calendar")
    if not cal:
        return {}
    result = cal.get_today_events()
    if result.get("status") == "ok":
        return {"calendar": result.get("data", {})}
    return {"calendar": {"error": result.get("error", "Failed to fetch")}}


def _collect_gmail_data(registry: AgentRegistry) -> dict:
    """Collect emails needing action."""
    gmail = registry.get("gmail")
    if not gmail:
        return {}
    result = gmail.get_action_needed_emails()
    if result.get("status") == "ok":
        return {"gmail": result.get("data", {})}
    return {"gmail": {"error": result.get("error", "Failed to fetch")}}


# ── Briefing Synthesis ──────────────────────────────────────────

MORNING_SYSTEM_PROMPT = """You are a personal operations assistant. You generate concise, action-oriented morning briefings.

Your job is NOT to list every piece of data. Your job is to RECOMMEND what to do first, second, third.

Output valid markdown with these sections (skip empty ones):

## Recommended Actions
1. Numbered list of what to tackle today, in priority order
   - Factor in: meetings (avoid deep work before meetings), blockers, pending reviews, emails needing reply
   - Each item: what to do, why it matters, ticket/PR/email reference

## Today's Schedule
- List meetings with times. Flag free time blocks for deep work.

## Important Updates
- Key things that changed overnight — Slack mentions, email replies, Jira comments, PR reviews
- Only include updates that require attention — skip noise

## Blockers
- List only if there are actual blockers: **[KEY]** Description

## Pending Replies
- Emails, Slack DMs, or PR reviews waiting on you

## Reminders
- Due or overdue personal reminders

Rules:
- Be opinionated — tell me what to do, don't just list things
- Use bullet lists, NOT tables
- Skip sections with no data
- Never fabricate IDs, names, or references
- Keep it under 400 words — I'll ask for details if needed
- Bold the ticket keys and PR numbers"""


EOD_SYSTEM_PROMPT = """You are a personal operations assistant. Generate a brief end-of-day summary.

Focus on: what's still open, what needs follow-up tomorrow, and any blockers carried over.

Output valid markdown:

## Still Open
- Tickets/PRs that need continued work tomorrow

## Carry-Over Blockers
- Only if there are unresolved blockers

## Tomorrow's Top 3
1. Three most important things to start with tomorrow

Rules:
- Use bullet lists, NOT tables
- Be brief — 150 words max
- Skip empty sections
- Never fabricate data"""


BLOCKER_SYSTEM_PROMPT = """List active blockers from the data. Output valid markdown.

Format each as:
- **[TICKET-KEY]** Description — Assignee (Priority)

If there are no blockers, say "No active blockers." only.
Be extremely concise."""


def _collect_reminders() -> list[dict]:
    """Fetch due reminders from the conductor's reminder store."""
    # Planner runs in a separate container — fetch reminders via conductor API
    import requests as _req
    conductor_url = os.getenv("CONDUCTOR_URL", "http://conductor:10000")
    try:
        resp = _req.get(
            f"{conductor_url}/reminders/due",
            headers={"x-api-key": AGENT_API_KEY},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("reminders", [])
    except Exception:
        pass
    return []


def build_morning_briefing() -> dict:
    """Build a full morning briefing by collecting data from all agents and synthesizing."""
    registry = get_registry()
    now = datetime.now(timezone.utc)

    # Collect raw data from all agents
    jira_data = _collect_jira_data(registry)
    github_data = _collect_github_data(registry)
    infra_data = _collect_infra_data(registry)
    slack_data = _collect_slack_data(registry)
    calendar_data = _collect_calendar_data(registry)
    gmail_data = _collect_gmail_data(registry)
    reminders = _collect_reminders()

    # Build context for LLM
    raw_context = _format_raw_context(
        jira_data, github_data, infra_data,
        slack_data=slack_data, calendar_data=calendar_data,
        gmail_data=gmail_data, reminders=reminders,
    )

    # Synthesize with LLM
    client = get_llm_client()
    markdown = client.complete(
        messages=[{"role": "user", "content": f"Generate my morning briefing for {now.strftime('%A, %B %d')}. Tell me what to do today.\n\nRaw data:\n{raw_context}"}],
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
            "slack": slack_data,
            "calendar": calendar_data,
            "gmail": gmail_data,
            "reminders": reminders,
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
        messages=[{"role": "user", "content": f"Generate my end-of-day summary for {now.strftime('%A, %B %d')}.\n\nRaw data:\n{raw_context}"}],
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

def _format_raw_context(
    jira_data: dict, github_data: dict, infra_data: dict,
    slack_data: dict | None = None, calendar_data: dict | None = None,
    gmail_data: dict | None = None, reminders: list | None = None,
) -> str:
    """Format collected raw data into a text context for LLM."""
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
                parts.append(f"\nYour open tickets ({len(my_tickets)}):")
                for t in my_tickets:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Status: {t.get('status', '?')} | Priority: {t.get('priority', '?')}")

            blocked = standup.get("blocked_tickets", [])
            if blocked:
                parts.append(f"\nBlocked tickets ({len(blocked)}):")
                for t in blocked:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Assignee: {t.get('assignee', '?')} | Priority: {t.get('priority', '?')}")

            stale = standup.get("stale_tickets", [])
            if stale:
                parts.append(f"\nStale tickets ({len(stale)}):")
                for t in stale:
                    parts.append(f"- [{t.get('key', '?')}] {t.get('summary', '?')} | Last updated: {t.get('updated', '?')}")

            # Recent activity from standup data
            activity = standup.get("recent_activity", [])
            if activity:
                parts.append(f"\nRecent activity by others ({len(activity)} items):")
                for a in activity:
                    line = f"- [{a.get('key', '?')}] {a.get('summary', '?')} | Status: {a.get('status', '?')}"
                    comment = a.get("latest_comment")
                    if comment:
                        line += f" | Comment by {comment.get('author', '?')}: \"{comment.get('body', '')[:100]}\""
                    parts.append(line)
        else:
            parts.append(f"Error fetching standup: {standup}")

        # Notification data (mentions + extra activity)
        notifs = data.get("notifications", {})
        if isinstance(notifs, dict) and "error" not in notifs:
            mentioned = notifs.get("mentioned", [])
            if mentioned:
                parts.append(f"\nTickets where you were mentioned ({len(mentioned)}):")
                for m in mentioned:
                    line = f"- [{m.get('key', '?')}] {m.get('summary', '?')}"
                    comment = m.get("latest_comment")
                    if comment:
                        line += f" | {comment.get('author', '?')}: \"{comment.get('body', '')[:100]}\""
                    parts.append(line)

            recent = notifs.get("recent_activity", [])
            if recent and not (isinstance(standup, dict) and standup.get("recent_activity")):
                parts.append(f"\nRecent updates in your projects ({len(recent)}):")
                for a in recent[:10]:
                    line = f"- [{a.get('key', '?')}] {a.get('summary', '?')} | {a.get('status', '?')}"
                    comment = a.get("latest_comment")
                    if comment:
                        line += f" | {comment.get('author', '?')}: \"{comment.get('body', '')[:80]}\""
                    parts.append(line)

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

    # Calendar section
    if calendar_data:
        cal = calendar_data.get("calendar", {})
        if isinstance(cal, dict) and "error" not in cal:
            events = cal.get("events", [])
            if events:
                parts.append("\n\n## TODAY'S CALENDAR")
                for e in events:
                    start = e.get("start_time", "")
                    summary = e.get("summary", "No title")
                    location = e.get("location", "")
                    link = e.get("hangout_link", "")
                    line = f"- {start[:16]} — {summary}"
                    if location:
                        line += f" ({location})"
                    if link:
                        line += f" [link]"
                    parts.append(line)

    # Slack section
    if slack_data:
        parts.append("\n\n## SLACK HIGHLIGHTS")
        for agent_id, data in slack_data.items():
            if isinstance(data, dict) and "error" not in data:
                mentions = data.get("mentions", [])
                dms = data.get("direct_messages", [])
                summary = data.get("summary", {})

                if mentions:
                    parts.append(f"\nMentions ({len(mentions)}):")
                    for m in mentions[:8]:
                        parts.append(f"- #{m.get('channel', '?')} — {m.get('author', '?')}: \"{m.get('text', '')[:100]}\"")

                if dms:
                    parts.append(f"\nDirect Messages ({len(dms)}):")
                    for d in dms[:5]:
                        parts.append(f"- {d.get('author', '?')}: \"{d.get('text', '')[:100]}\"")

    # Gmail section
    if gmail_data:
        gmail = gmail_data.get("gmail", {})
        if isinstance(gmail, dict) and "error" not in gmail:
            emails = gmail.get("emails", [])
            if emails:
                parts.append(f"\n\n## EMAILS NEEDING ACTION ({len(emails)})")
                for e in emails[:8]:
                    parts.append(f"- From: {e.get('from', '?')} — {e.get('subject', 'No subject')}")
                    snippet = e.get("snippet", "")
                    if snippet:
                        parts.append(f"  Preview: \"{snippet[:100]}\"")

    # Reminders section
    if reminders:
        parts.append(f"\n\n## DUE REMINDERS ({len(reminders)})")
        for r in reminders:
            line = f"- {r.get('title', '?')}"
            if r.get("due_at"):
                line += f" (due: {r['due_at']})"
            if r.get("priority") and r["priority"] != "normal":
                line += f" [{r['priority']}]"
            parts.append(line)

    return "\n".join(parts)
