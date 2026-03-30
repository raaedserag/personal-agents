import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

JIRA_DOMAIN = os.getenv("JIRA_DOMAIN", "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

_auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
_headers = {"Accept": "application/json", "Content-Type": "application/json"}


def _jira_request(method, endpoint, **kwargs):
    url = f"{JIRA_DOMAIN}/rest/api/3/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(
            method,
            url,
            auth=_auth,
            headers=_headers,
            timeout=15,
            **kwargs,
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


def _parse_ticket(issue):
    fields = issue.get("fields", {})
    assignee = fields.get("assignee")
    assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
    priority = fields.get("priority")
    priority_name = priority.get("name", "None") if priority else "None"
    status = fields.get("status", {}).get("name", "Unknown")
    return (
        f"[{issue['key']}] {fields.get('summary', 'No summary')}\n"
        f"  Status: {status} | Assignee: {assignee_name} | Priority: {priority_name}"
    )


def _parse_ticket_detail(issue):
    fields = issue.get("fields", {})
    assignee = fields.get("assignee")
    assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
    priority = fields.get("priority")
    priority_name = priority.get("name", "None") if priority else "None"
    status = fields.get("status", {}).get("name", "Unknown")
    project = fields.get("project", {}).get("key", "?")

    desc_doc = fields.get("description")
    description = _extract_adf_text(desc_doc) if desc_doc else "No description."

    comments_data = fields.get("comment", {}).get("comments", [])
    recent_comments = comments_data[-3:]
    comment_lines = []
    for c in recent_comments:
        author = c.get("author", {}).get("displayName", "Unknown")
        body = _extract_adf_text(c.get("body", {}))
        comment_lines.append(f"  - {author}: {body}")
    comments_str = "\n".join(comment_lines) if comment_lines else "  No comments."

    return (
        f"[{issue['key']}] {fields.get('summary', 'No summary')}\n"
        f"  Project: {project} | Status: {status} | Assignee: {assignee_name} | Priority: {priority_name}\n"
        f"  Description: {description}\n"
        f"  Recent Comments:\n{comments_str}"
    )


def _extract_adf_text(adf_node):
    if not isinstance(adf_node, dict):
        return str(adf_node)[:500]
    texts = []
    if adf_node.get("type") == "text":
        texts.append(adf_node.get("text", ""))
    for child in adf_node.get("content", []):
        texts.append(_extract_adf_text(child))
    return " ".join(texts).strip()[:500]


# ─── Read Operations ──────────────────────────────────────────────

def get_my_open_tickets(max_results="10"):
    max_results = int(max_results)
    jql = "assignee = currentUser() AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
    data = _jira_request("POST", "search/jql", json={"jql": jql, "maxResults": max_results, "fields": ["summary", "status", "assignee", "priority"]})
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return "No open tickets assigned to you."
    lines = [_parse_ticket(i) for i in issues]
    return f"Found {len(issues)} open ticket(s):\n\n" + "\n\n".join(lines)


def get_team_open_tickets(project_key, max_results="20"):
    max_results = int(max_results)
    jql = f"project = {project_key} AND resolution = Unresolved ORDER BY priority DESC, updated DESC"
    data = _jira_request("POST", "search/jql", json={"jql": jql, "maxResults": max_results, "fields": ["summary", "status", "assignee", "priority"]})
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return f"No open tickets in project {project_key}."
    lines = [_parse_ticket(i) for i in issues]
    return f"Found {len(issues)} open ticket(s) in {project_key}:\n\n" + "\n\n".join(lines)


def get_ticket_details(issue_key):
    data = _jira_request("GET", f"issue/{issue_key}", params={"fields": "summary,status,assignee,priority,description,comment,project"})
    if "error" in data:
        return f"Error: {data['error']}"
    return _parse_ticket_detail(data)


def search_tickets(query, project_key=""):
    jql_parts = [f'text ~ "{query}"']
    if project_key:
        jql_parts.append(f"project = {project_key}")
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    data = _jira_request("POST", "search/jql", json={"jql": jql, "maxResults": 10, "fields": ["summary", "status", "assignee", "priority"]})
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        return f"No tickets found matching '{query}'."
    lines = [_parse_ticket(i) for i in issues]
    return f"Found {len(issues)} ticket(s) for '{query}':\n\n" + "\n\n".join(lines)


def get_blocked_tickets(project_key=""):
    jql = "status = Blocked"
    if project_key:
        jql += f" AND project = {project_key}"
    jql += " ORDER BY priority DESC, updated DESC"
    data = _jira_request("POST", "search/jql", json={"jql": jql, "maxResults": 20, "fields": ["summary", "status", "assignee", "priority"]})
    if "error" in data:
        return f"Error: {data['error']}"
    issues = data.get("issues", [])
    if not issues:
        scope = f"in project {project_key}" if project_key else "across all projects"
        return f"No blocked tickets {scope}."
    lines = [_parse_ticket(i) for i in issues]
    return f"Found {len(issues)} blocked ticket(s):\n\n" + "\n\n".join(lines)


# ─── Write Operations (called only after user confirmation) ──────

def _get_transitions(issue_key):
    data = _jira_request("GET", f"issue/{issue_key}/transitions")
    if "error" in data:
        return None, f"Error: {data['error']}"
    transitions = data.get("transitions", [])
    return transitions, None


def transition_ticket(issue_key, target_status):
    transitions, err = _get_transitions(issue_key)
    if err:
        return err
    match = None
    for t in transitions:
        if t["name"].lower() == target_status.lower():
            match = t
            break
    if not match:
        available = ", ".join(t["name"] for t in transitions)
        return f"Cannot transition {issue_key} to '{target_status}'. Available transitions: {available}"
    data = _jira_request("POST", f"issue/{issue_key}/transitions", json={"transition": {"id": match["id"]}})
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return f"Successfully transitioned {issue_key} to '{target_status}'."


def add_comment(issue_key, comment_body):
    adf_body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment_body}],
                }
            ],
        }
    }
    data = _jira_request("POST", f"issue/{issue_key}/comment", json=adf_body)
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return f"Comment added to {issue_key}."


def assign_ticket(issue_key, assignee_email):
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


def create_ticket(project_key, summary, description="", issue_type="Task"):
    desc_adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": description}] if description else [],
            }
        ],
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
