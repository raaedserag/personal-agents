"""
Jira Fetcher — All Jira API interactions.

Generalized from the original zeal-jira-agent. Reads credentials from
environment variables (injected per-profile via Docker Compose).

Supports JIRA_PROJECT_KEYS to scope queries to specific boards.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests
from requests.auth import HTTPBasicAuth

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# Configurable project filter — comma-separated project keys (e.g., "EXDR,PLAT")
# If empty, queries are unscoped (all projects).
JIRA_PROJECT_KEYS = [
    k.strip() for k in os.getenv("JIRA_PROJECT_KEYS", "").split(",") if k.strip()
]

_auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
_headers = {"Accept": "application/json", "Content-Type": "application/json"}


def _project_jql_clause() -> str:
    """Build a JQL clause to scope queries to configured projects."""
    if not JIRA_PROJECT_KEYS:
        return ""
    if len(JIRA_PROJECT_KEYS) == 1:
        return f"project = {JIRA_PROJECT_KEYS[0]}"
    keys = ", ".join(JIRA_PROJECT_KEYS)
    return f"project in ({keys})"


def _and_project(jql: str) -> str:
    """Prepend project filter to a JQL query."""
    clause = _project_jql_clause()
    if not clause:
        return jql
    return f"{clause} AND {jql}"


def _jira_request(method: str, endpoint: str, **kwargs) -> dict:
    url = f"{JIRA_DOMAIN}/rest/api/3/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(
            method, url, auth=_auth, headers=_headers, timeout=15, **kwargs,
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        body = ""
        if e.response is not None:
            try:
                body = e.response.json().get("errorMessages", [e.response.text])
            except Exception:
                body = e.response.text[:300]
        return {"error": f"HTTP {status}: {body}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed — is JIRA_DOMAIN correct?"}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out after 15s."}


# ── Parsing Helpers ──────────────────────────────────────────────

def _parse_ticket(issue: dict) -> dict:
    """Parse a Jira issue into a standardized dict."""
    fields = issue.get("fields", {})
    assignee = fields.get("assignee")
    priority = fields.get("priority")
    return {
        "key": issue["key"],
        "summary": fields.get("summary", "No summary"),
        "status": fields.get("status", {}).get("name", "Unknown"),
        "assignee": assignee.get("displayName", "Unassigned") if assignee else "Unassigned",
        "priority": priority.get("name", "None") if priority else "None",
        "project": fields.get("project", {}).get("key", ""),
        "updated": fields.get("updated", ""),
    }


def _parse_ticket_detail(issue: dict) -> dict:
    """Parse a Jira issue with full details."""
    base = _parse_ticket(issue)
    fields = issue.get("fields", {})

    desc_doc = fields.get("description")
    description = _extract_adf_text(desc_doc) if desc_doc else "No description."

    comments_data = fields.get("comment", {}).get("comments", [])
    recent_comments = comments_data[-3:]
    comments = []
    for c in recent_comments:
        comments.append({
            "author": c.get("author", {}).get("displayName", "Unknown"),
            "body": _extract_adf_text(c.get("body", {})),
            "created": c.get("created", ""),
        })

    return {**base, "description": description, "comments": comments}


def _format_ticket(ticket: dict) -> str:
    """Format a ticket dict as a readable string."""
    return (
        f"[{ticket['key']}] {ticket['summary']}\n"
        f"  Status: {ticket['status']} | Assignee: {ticket['assignee']} | Priority: {ticket['priority']}"
    )


def _format_ticket_detail(ticket: dict) -> str:
    """Format a detailed ticket dict as a readable string."""
    comment_lines = []
    for c in ticket.get("comments", []):
        comment_lines.append(f"  - {c['author']}: {c['body']}")
    comments_str = "\n".join(comment_lines) if comment_lines else "  No comments."

    return (
        f"[{ticket['key']}] {ticket['summary']}\n"
        f"  Project: {ticket['project']} | Status: {ticket['status']} | "
        f"Assignee: {ticket['assignee']} | Priority: {ticket['priority']}\n"
        f"  Description: {ticket['description']}\n"
        f"  Recent Comments:\n{comments_str}"
    )


def _extract_adf_text(adf_node: dict | str) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not isinstance(adf_node, dict):
        return str(adf_node)[:500]
    texts = []
    if adf_node.get("type") == "text":
        texts.append(adf_node.get("text", ""))
    for child in adf_node.get("content", []):
        texts.append(_extract_adf_text(child))
    return " ".join(texts).strip()[:500]


# ── Read Operations ──────────────────────────────────────────────

def get_my_open_tickets(max_results: str = "10") -> str:
    max_results_int = int(max_results)
    jql = _and_project("assignee = currentUser() AND resolution = Unresolved ORDER BY priority DESC, updated DESC")
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": max_results_int,
              "fields": ["summary", "status", "assignee", "priority", "project", "updated"]},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return "No open tickets assigned to you."
    tickets = [_parse_ticket(i) for i in issues]
    lines = [_format_ticket(t) for t in tickets]
    return f"Found {len(issues)} open ticket(s):\n\n" + "\n\n".join(lines)


def get_my_open_tickets_structured(max_results: int = 20) -> list[dict]:
    """Returns structured ticket data (for API/planner consumption)."""
    jql = _and_project("assignee = currentUser() AND resolution = Unresolved ORDER BY priority DESC, updated DESC")
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": max_results,
              "fields": ["summary", "status", "assignee", "priority", "project", "updated"]},
    )
    if "error" in data:
        return []
    return [_parse_ticket(i) for i in data.get("issues", [])]


def get_team_open_tickets(project_key: str, max_results: str = "20") -> str:
    max_results_int = int(max_results)
    jql = f"project = {project_key} AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": max_results_int,
              "fields": ["summary", "status", "assignee", "priority", "project", "updated"]},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return f"No open tickets in project {project_key}."
    tickets = [_parse_ticket(i) for i in issues]
    lines = [_format_ticket(t) for t in tickets]
    return f"Found {len(issues)} open ticket(s) in {project_key}:\n\n" + "\n\n".join(lines)


def get_ticket_details(issue_key: str) -> str:
    data = _jira_request(
        "GET", f"issue/{issue_key}",
        params={"fields": "summary,status,assignee,priority,description,comment,project"},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    return _format_ticket_detail(_parse_ticket_detail(data))


def search_tickets(query: str, project_key: str = "") -> str:
    jql_parts = [f'text ~ "{query}"']
    if project_key:
        jql_parts.append(f"project = {project_key}")
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    # Apply project filter if no explicit project was given
    if not project_key:
        jql = _and_project(jql)
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": 10,
              "fields": ["summary", "status", "assignee", "priority", "project"]},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return f"No tickets found matching '{query}'."
    tickets = [_parse_ticket(i) for i in issues]
    lines = [_format_ticket(t) for t in tickets]
    return f"Found {len(issues)} ticket(s) for '{query}':\n\n" + "\n\n".join(lines)


def get_blocked_tickets(project_key: str = "") -> str:
    jql = "status = Blocked"
    if project_key:
        jql += f" AND project = {project_key}"
    jql += " ORDER BY priority DESC, updated DESC"
    if not project_key:
        jql = _and_project(jql)
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": 20,
              "fields": ["summary", "status", "assignee", "priority", "project"]},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        scope = f"in project {project_key}" if project_key else "across configured projects"
        return f"No blocked tickets {scope}."
    tickets = [_parse_ticket(i) for i in issues]
    lines = [_format_ticket(t) for t in tickets]
    return f"Found {len(issues)} blocked ticket(s):\n\n" + "\n\n".join(lines)


def get_blocked_tickets_structured(project_key: str = "", my_only: bool = False) -> list[dict]:
    """Returns structured blocked ticket data.

    Args:
        project_key: Filter to a specific project.
        my_only: If True, only return blocked tickets assigned to current user
                 (for individual/IC scope — you don't care about team blockers).
    """
    jql = "status = Blocked"
    if my_only:
        jql += " AND assignee = currentUser()"
    if project_key:
        jql += f" AND project = {project_key}"
    jql += " ORDER BY priority DESC, updated DESC"
    if not project_key:
        jql = _and_project(jql)
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": 20,
              "fields": ["summary", "status", "assignee", "priority", "project", "updated"]},
    )
    if "error" in data:
        return []
    return [_parse_ticket(i) for i in data.get("issues", [])]


def get_stale_tickets(days: int = 3, project_key: str = "") -> list[dict]:
    """Find tickets with no updates in N days (leader scope feature)."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    jql = f"resolution = Unresolved AND updated <= '{since}'"
    if project_key:
        jql += f" AND project = {project_key}"
    jql += " ORDER BY updated ASC"
    if not project_key:
        jql = _and_project(jql)
    data = _jira_request(
        "POST", "search/jql",
        json={"jql": jql, "maxResults": 30,
              "fields": ["summary", "status", "assignee", "priority", "project", "updated"]},
    )
    if "error" in data:
        return []
    return [_parse_ticket(i) for i in data.get("issues", [])]


# ── Notifications / Recent Activity ─────────────────────────────

def get_recent_activity(hours: int = 24, max_results: int = 15) -> list[dict]:
    """Fetch recently updated tickets (by others) in configured projects.

    This surfaces important activity: comments, status changes, new assignments
    that happened while you weren't looking. Like a smart notification feed.
    """
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    # Tickets updated recently by someone other than me, in my projects
    jql = f'updated >= "{since}" AND updatedBy != currentUser()'
    jql = _and_project(jql)
    jql += " ORDER BY updated DESC"

    data = _jira_request(
        "POST", "search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "project",
                        "updated", "comment", "creator"],
        },
    )
    if "error" in data:
        return []

    activities = []
    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        ticket = _parse_ticket(issue)

        # Extract the latest comment (if any, from the last 24h)
        comments_data = fields.get("comment", {}).get("comments", [])
        latest_comment = None
        for c in reversed(comments_data):
            created = c.get("created", "")
            author = c.get("author", {}).get("displayName", "Unknown")
            # Include comments from others only
            if JIRA_EMAIL and c.get("author", {}).get("emailAddress", "") == JIRA_EMAIL:
                continue
            latest_comment = {
                "author": author,
                "body": _extract_adf_text(c.get("body", {}))[:200],
                "created": created,
            }
            break

        activities.append({
            **ticket,
            "latest_comment": latest_comment,
        })

    return activities


def get_mentioned_tickets(days: int = 7, max_results: int = 10) -> list[dict]:
    """Find tickets where current user was mentioned in comments recently."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    # Note: "currentUser()" in text search looks for mentions in comments/description
    jql = f'updated >= "{since}" AND comment ~ "currentUser()"'
    jql = _and_project(jql)
    jql += " ORDER BY updated DESC"

    data = _jira_request(
        "POST", "search/jql",
        json={
            "jql": jql,
            "maxResults": max_results,
            "fields": ["summary", "status", "assignee", "priority", "project",
                        "updated", "comment"],
        },
    )
    if "error" in data:
        return []

    results = []
    for issue in data.get("issues", []):
        ticket = _parse_ticket(issue)
        comments_data = issue.get("fields", {}).get("comment", {}).get("comments", [])
        latest = comments_data[-1] if comments_data else None
        ticket["latest_comment"] = {
            "author": latest.get("author", {}).get("displayName", "Unknown"),
            "body": _extract_adf_text(latest.get("body", {}))[:200],
            "created": latest.get("created", ""),
        } if latest else None
        results.append(ticket)

    return results


# ── Write Operations ─────────────────────────────────────────────

def _get_transitions(issue_key: str) -> tuple[list | None, str | None]:
    data = _jira_request("GET", f"issue/{issue_key}/transitions")
    if "error" in data:
        return None, f"Error: {data['error']}"
    return data.get("transitions", []), None


def transition_ticket(issue_key: str, target_status: str) -> str:
    transitions, err = _get_transitions(issue_key)
    if err:
        return err
    match = None
    for t in transitions:
        if t["name"].lower() == target_status.lower():
            match = t
            break
    if not match:
        available = ", ".join(t["name"] for t in (transitions or []))
        return f"Cannot transition {issue_key} to '{target_status}'. Available: {available}"
    data = _jira_request("POST", f"issue/{issue_key}/transitions", json={"transition": {"id": match["id"]}})
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return f"Successfully transitioned {issue_key} to '{target_status}'."


def add_comment(issue_key: str, comment_body: str) -> str:
    adf_body = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_body}]}],
        }
    }
    data = _jira_request("POST", f"issue/{issue_key}/comment", json=adf_body)
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return f"Comment added to {issue_key}."


def assign_ticket(issue_key: str, assignee_email: str) -> str:
    data = _jira_request("GET", "user/search", params={"query": assignee_email, "maxResults": 1})
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    if isinstance(data, list) and len(data) > 0:
        account_id = data[0].get("accountId")
    else:
        return f"User '{assignee_email}' not found in Jira."
    result = _jira_request("PUT", f"issue/{issue_key}/assignee", json={"accountId": account_id})
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    return f"Assigned {issue_key} to {assignee_email}."


def create_ticket(project_key: str, summary: str, description: str = "", issue_type: str = "Task") -> str:
    desc_adf = {
        "type": "doc", "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}] if description else []}],
    }
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": desc_adf,
            "issuetype": {"name": issue_type},
        }
    }
    data = _jira_request("POST", "issue", json=payload)
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    new_key = data.get("key", "?")
    return f"Created ticket {new_key} in project {project_key}: {summary}"
