"""
GitHub Fetcher — All GitHub API interactions.

Reads credentials from environment variables (injected per-profile via Docker Compose).
Handles PR listing, details, stale PR detection, and CI status.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORG = os.getenv("GITHUB_ORG", "")
GITHUB_REPOS = os.getenv("GITHUB_REPOS", "")  # comma-separated, empty = all org repos
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

_BASE = "https://api.github.com"


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _gh_request(method: str, path: str, **kwargs) -> dict | list:
    url = f"{_BASE}/{path.lstrip('/')}"
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("headers", _headers())
    try:
        resp = requests.request(method, url, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        body = ""
        if e.response is not None:
            try:
                body = e.response.json().get("message", e.response.text[:300])
            except Exception:
                body = e.response.text[:300]
        return {"error": f"HTTP {status}: {body}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed — check network or GitHub token."}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out after 20s."}


# ── Repo Discovery ──────────────────────────────────────────────

def _get_configured_repos() -> list[str]:
    """Get the list of repos to monitor. Format: 'owner/repo'."""
    if GITHUB_REPOS:
        repos = [r.strip() for r in GITHUB_REPOS.split(",") if r.strip()]
        # If repos don't contain '/', prefix with org
        return [r if "/" in r else f"{GITHUB_ORG}/{r}" for r in repos]

    if not GITHUB_ORG:
        return []

    # Fetch all org repos
    data = _gh_request("GET", f"orgs/{GITHUB_ORG}/repos", params={
        "type": "all", "sort": "updated", "per_page": 50,
    })
    if isinstance(data, dict) and "error" in data:
        return []
    return [r["full_name"] for r in data if isinstance(r, dict)]


# ── Parsing Helpers ─────────────────────────────────────────────

def _parse_pr(pr: dict, repo_full_name: str = "") -> dict:
    """Parse a GitHub PR into a standardized dict."""
    user = pr.get("user", {})
    reviewers = [r.get("login", "") for r in pr.get("requested_reviewers", [])]

    status = "open"
    if pr.get("draft"):
        status = "draft"
    elif pr.get("merged"):
        status = "merged"
    elif pr.get("state") == "closed":
        status = "closed"

    repo = repo_full_name or pr.get("base", {}).get("repo", {}).get("full_name", "")

    return {
        "repo": repo,
        "number": pr.get("number", 0),
        "title": pr.get("title", ""),
        "author": user.get("login", "unknown"),
        "status": status,
        "reviewers": reviewers,
        "ci_status": "unknown",  # filled separately
        "created_at": pr.get("created_at", ""),
        "updated_at": pr.get("updated_at", ""),
        "url": pr.get("html_url", ""),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changed_files": pr.get("changed_files", 0),
        "body": (pr.get("body") or "")[:500],
    }


def _format_pr(pr: dict) -> str:
    """Format a PR dict as a readable string."""
    reviewers_str = ", ".join(pr["reviewers"]) if pr["reviewers"] else "none"
    return (
        f"[{pr['repo']}#{pr['number']}] {pr['title']}\n"
        f"  Author: {pr['author']} | Status: {pr['status']} | "
        f"CI: {pr['ci_status']} | Reviewers: {reviewers_str}\n"
        f"  {pr['url']}"
    )


# ── Read Operations ─────────────────────────────────────────────

def get_open_prs(
    repo: str = "",
    author: str = "",
    reviewer: str = "",
    max_results: int = 30,
) -> list[dict]:
    """Get open PRs, optionally filtered by repo/author/reviewer."""
    repos = [repo] if repo else _get_configured_repos()
    all_prs: list[dict] = []

    for repo_name in repos:
        if "/" not in repo_name:
            continue
        owner, rname = repo_name.split("/", 1)
        data = _gh_request("GET", f"repos/{owner}/{rname}/pulls", params={
            "state": "open", "sort": "updated", "direction": "desc", "per_page": 50,
        })
        if isinstance(data, dict) and "error" in data:
            continue
        for pr in data:
            parsed = _parse_pr(pr, repo_name)
            if author and parsed["author"] != author:
                continue
            if reviewer and reviewer not in parsed["reviewers"]:
                continue
            all_prs.append(parsed)

    all_prs.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return all_prs[:max_results]


def get_open_prs_formatted(
    repo: str = "",
    author: str = "",
    reviewer: str = "",
) -> str:
    """Get open PRs as formatted text."""
    prs = get_open_prs(repo, author, reviewer)
    if not prs:
        filters = []
        if repo:
            filters.append(f"repo={repo}")
        if author:
            filters.append(f"author={author}")
        if reviewer:
            filters.append(f"reviewer={reviewer}")
        filter_str = f" ({', '.join(filters)})" if filters else ""
        return f"No open PRs found{filter_str}."

    lines = [_format_pr(p) for p in prs]
    return f"Found {len(prs)} open PR(s):\n\n" + "\n\n".join(lines)


def get_pr_details(owner: str, repo: str, pr_number: int) -> dict:
    """Get full details for a specific PR."""
    data = _gh_request("GET", f"repos/{owner}/{repo}/pulls/{pr_number}")
    if isinstance(data, dict) and "error" in data:
        return data
    return _parse_pr(data, f"{owner}/{repo}")


def get_pr_details_formatted(owner: str, repo: str, pr_number: int) -> str:
    """Get PR details as formatted text."""
    pr = get_pr_details(owner, repo, pr_number)
    if "error" in pr:
        return f"Error: {pr['error']}"

    body = pr.get("body", "No description.")
    reviewers_str = ", ".join(pr["reviewers"]) if pr["reviewers"] else "none"

    return (
        f"[{pr['repo']}#{pr['number']}] {pr['title']}\n"
        f"  Author: {pr['author']} | Status: {pr['status']} | CI: {pr['ci_status']}\n"
        f"  Reviewers: {reviewers_str}\n"
        f"  Changes: +{pr.get('additions', '?')} -{pr.get('deletions', '?')} "
        f"({pr.get('changed_files', '?')} files)\n"
        f"  Created: {pr['created_at']} | Updated: {pr['updated_at']}\n"
        f"  URL: {pr['url']}\n"
        f"  Description: {body}"
    )


def get_pr_diff(owner: str, repo: str, pr_number: int) -> str:
    """Get the diff for a PR (for summarization)."""
    url = f"{_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = _headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        diff = resp.text
        # Truncate very large diffs
        if len(diff) > 15000:
            diff = diff[:15000] + "\n\n... [diff truncated, too large for summarization]"
        return diff
    except Exception as e:
        return f"Error fetching diff: {e}"


def get_stale_prs(days: int = 5) -> list[dict]:
    """Find PRs with no activity in N days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.isoformat()
    all_prs = get_open_prs()
    stale = [
        p for p in all_prs
        if p.get("updated_at", "") and p["updated_at"] < cutoff_str
    ]
    return stale


def get_stale_prs_formatted(days: int = 5) -> str:
    """Get stale PRs as formatted text."""
    prs = get_stale_prs(days)
    if not prs:
        return f"No stale PRs (no PR inactive for {days}+ days)."
    lines = [_format_pr(p) for p in prs]
    return f"Found {len(prs)} stale PR(s) (no activity in {days}+ days):\n\n" + "\n\n".join(lines)


# ── CI Status ───────────────────────────────────────────────────

def get_ci_status(owner: str, repo: str, ref: str = "") -> dict:
    """Get combined CI status for a ref (branch or SHA)."""
    if not ref:
        ref = "main"
    data = _gh_request("GET", f"repos/{owner}/{repo}/commits/{ref}/status")
    if isinstance(data, dict) and "error" in data:
        return data

    # Also get check runs for GitHub Actions
    checks = _gh_request("GET", f"repos/{owner}/{repo}/commits/{ref}/check-runs")
    check_runs = []
    if isinstance(checks, dict) and "check_runs" in checks:
        for cr in checks["check_runs"]:
            check_runs.append({
                "name": cr.get("name", ""),
                "status": cr.get("status", ""),
                "conclusion": cr.get("conclusion", ""),
                "url": cr.get("html_url", ""),
            })

    return {
        "ref": ref,
        "state": data.get("state", "unknown"),
        "total_count": data.get("total_count", 0),
        "statuses": [
            {"context": s.get("context", ""), "state": s.get("state", ""), "description": s.get("description", "")}
            for s in data.get("statuses", [])
        ],
        "check_runs": check_runs,
    }


def get_ci_status_formatted(owner: str, repo: str, ref: str = "") -> str:
    """Get CI status as formatted text."""
    ci = get_ci_status(owner, repo, ref)
    if "error" in ci:
        return f"Error: {ci['error']}"

    lines = [f"CI Status for {owner}/{repo} @ {ci['ref']}: {ci['state']}"]

    for s in ci.get("statuses", []):
        icon = "+" if s["state"] == "success" else "-" if s["state"] == "failure" else "?"
        lines.append(f"  [{icon}] {s['context']}: {s['state']}")

    for cr in ci.get("check_runs", []):
        conclusion = cr["conclusion"] or cr["status"]
        icon = "+" if conclusion == "success" else "-" if conclusion == "failure" else "?"
        lines.append(f"  [{icon}] {cr['name']}: {conclusion}")

    return "\n".join(lines)


def get_pr_ci_status(owner: str, repo: str, pr_number: int) -> str:
    """Get CI status for a specific PR's head commit."""
    pr_data = _gh_request("GET", f"repos/{owner}/{repo}/pulls/{pr_number}")
    if isinstance(pr_data, dict) and "error" in pr_data:
        return "unknown"
    head_sha = pr_data.get("head", {}).get("sha", "")
    if not head_sha:
        return "unknown"
    ci = get_ci_status(owner, repo, head_sha)
    return ci.get("state", "unknown")


def enrich_prs_with_ci(prs: list[dict]) -> list[dict]:
    """Add CI status to a list of PRs. Best-effort, skips on error."""
    for pr in prs:
        repo = pr.get("repo", "")
        if "/" not in repo:
            continue
        owner, rname = repo.split("/", 1)
        pr["ci_status"] = get_pr_ci_status(owner, rname, pr["number"])
    return prs


# ── Review Quality Check ────────────────────────────────────────

def check_pr_quality(owner: str, repo: str, pr_number: int) -> dict:
    """Flag quality issues: no description, no tests, huge diff."""
    pr = get_pr_details(owner, repo, pr_number)
    if "error" in pr:
        return pr

    issues: list[str] = []
    if not pr.get("body", "").strip():
        issues.append("No PR description")
    if pr.get("changed_files", 0) > 30:
        issues.append(f"Large PR: {pr['changed_files']} files changed")
    if pr.get("additions", 0) + pr.get("deletions", 0) > 1000:
        total = pr.get("additions", 0) + pr.get("deletions", 0)
        issues.append(f"Large diff: {total} lines changed")
    if not pr.get("reviewers"):
        issues.append("No reviewers assigned")

    return {
        "pr": f"{owner}/{repo}#{pr_number}",
        "title": pr.get("title", ""),
        "issues": issues,
        "quality": "ok" if not issues else "needs_attention",
    }


# ── Digest (for planner agent) ─────────────────────────────────

def build_pr_digest(profile_id: str = "", include_ci: bool = False) -> dict:
    """Build a structured PR digest for the planner agent."""
    username = GITHUB_USERNAME

    all_prs = get_open_prs()

    # Optionally enrich with CI — slower but more useful
    if include_ci and len(all_prs) <= 15:
        all_prs = enrich_prs_with_ci(all_prs)

    my_prs = [p for p in all_prs if p["author"] == username] if username else []
    review_requested = [p for p in all_prs if username and username in p.get("reviewers", [])]
    stale = get_stale_prs(days=5)

    return {
        "profile_id": profile_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "open_prs": [_slim_pr(p) for p in all_prs],
        "my_prs": [_slim_pr(p) for p in my_prs],
        "review_requested": [_slim_pr(p) for p in review_requested],
        "stale_prs": [_slim_pr(p) for p in stale],
    }


def _slim_pr(pr: dict) -> dict:
    """Strip large fields for digest payloads."""
    return {k: v for k, v in pr.items() if k != "body"}
