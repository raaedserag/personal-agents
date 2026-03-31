"""
GitHub Agent API — FastAPI endpoints.

Scope-aware: reads PROFILE_SCOPE env var to determine behavior.
- "individual": focuses on user's own PRs
- "leader": adds team-wide PR visibility, stale PR tracking
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query

sys.path.insert(0, "/app")
from shared.auth import verify_api_key
from shared.models import QueryResponse, PRSummary, PRDigest

from skills.github_fetcher import (
    get_open_prs,
    get_open_prs_formatted,
    get_pr_details_formatted,
    get_stale_prs,
    get_stale_prs_formatted,
    get_ci_status_formatted,
    get_pr_ci_status,
    check_pr_quality,
    build_pr_digest,
    enrich_prs_with_ci,
)
from skills.pr_summarizer import summarize_pr_formatted

load_dotenv()

PROFILE_ID = os.getenv("PROFILE_ID", "unknown")
PROFILE_SCOPE = os.getenv("PROFILE_SCOPE", "individual")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
AGENT_ID = f"github-{PROFILE_ID}"

app = FastAPI(
    title=f"Nerve Center GitHub Agent ({PROFILE_ID})",
    version="1.0.0",
    description=f"GitHub agent for profile '{PROFILE_ID}' (scope: {PROFILE_SCOPE})",
)


# ── Health ───────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "agent": AGENT_ID,
        "profile": PROFILE_ID,
        "scope": PROFILE_SCOPE,
        "version": "1.0.0",
    }


# ── PR Listing ───────────────────────────────────────────────────

@app.get("/prs/open")
def open_prs(
    author: str = Query(default=""),
    reviewer: str = Query(default=""),
    repo: str = Query(default=""),
    _key: str = Depends(verify_api_key),
):
    """List open PRs, optionally filtered by author/reviewer/repo."""
    prs = get_open_prs(repo=repo, author=author, reviewer=reviewer)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=prs)


@app.get("/prs/mine")
def my_prs(_key: str = Depends(verify_api_key)):
    """List open PRs authored by the configured user."""
    if not GITHUB_USERNAME:
        return QueryResponse(
            status="error", agent_id=AGENT_ID,
            error="GITHUB_USERNAME not configured.",
        )
    prs = get_open_prs(author=GITHUB_USERNAME)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=prs)


@app.get("/prs/review-requested")
def review_requested(_key: str = Depends(verify_api_key)):
    """List PRs where the configured user is a requested reviewer."""
    if not GITHUB_USERNAME:
        return QueryResponse(
            status="error", agent_id=AGENT_ID,
            error="GITHUB_USERNAME not configured.",
        )
    prs = get_open_prs(reviewer=GITHUB_USERNAME)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=prs)


# ── PR Details & Summary ────────────────────────────────────────

@app.get("/prs/{owner}/{repo}/{pr_number}")
def pr_details(
    owner: str,
    repo: str,
    pr_number: int,
    _key: str = Depends(verify_api_key),
):
    """Get full details for a specific PR."""
    result = get_pr_details_formatted(owner, repo, pr_number)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/prs/{owner}/{repo}/{pr_number}/summary")
def pr_summary(
    owner: str,
    repo: str,
    pr_number: int,
    _key: str = Depends(verify_api_key),
):
    """Get a Claude-powered summary of a PR's changes."""
    result = summarize_pr_formatted(owner, repo, pr_number)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


@app.get("/prs/{owner}/{repo}/{pr_number}/quality")
def pr_quality(
    owner: str,
    repo: str,
    pr_number: int,
    _key: str = Depends(verify_api_key),
):
    """Check PR quality (description, size, reviewers)."""
    result = check_pr_quality(owner, repo, pr_number)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Stale PRs ────────────────────────────────────────────────────

@app.get("/prs/stale")
def stale_prs(
    days: int = Query(default=5, ge=1, le=90),
    _key: str = Depends(verify_api_key),
):
    """Find PRs with no activity in N days."""
    prs = get_stale_prs(days)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=prs)


# ── CI Status ────────────────────────────────────────────────────

@app.get("/ci/status")
def ci_status(
    repo: str = Query(..., description="Full repo name: owner/repo"),
    ref: str = Query(default="main"),
    _key: str = Depends(verify_api_key),
):
    """Get CI status for a repo ref."""
    if "/" not in repo:
        return QueryResponse(
            status="error", agent_id=AGENT_ID,
            error="Repo must be in 'owner/repo' format.",
        )
    owner, rname = repo.split("/", 1)
    result = get_ci_status_formatted(owner, rname, ref)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


# ── Digest (for planner agent) ──────────────────────────────────

@app.get("/prs/digest")
def pr_digest(
    include_ci: bool = Query(default=False),
    _key: str = Depends(verify_api_key),
):
    """Build a structured PR digest for the planner agent."""
    digest = build_pr_digest(profile_id=PROFILE_ID, include_ci=include_ci)
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=digest)


# ── Query (natural language, for conductor routing) ──────────────

@app.post("/query")
def query_agent(
    query: str,
    profile_id: str = "",
    _key: str = Depends(verify_api_key),
):
    """Handle natural language queries routed from conductor."""
    q = query.lower()

    if "my pr" in q or "my pull" in q:
        if not GITHUB_USERNAME:
            return QueryResponse(status="error", agent_id=AGENT_ID, error="GITHUB_USERNAME not configured.")
        result = get_open_prs_formatted(author=GITHUB_USERNAME)
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "review" in q and ("request" in q or "need" in q or "waiting" in q):
        if GITHUB_USERNAME:
            result = get_open_prs_formatted(reviewer=GITHUB_USERNAME)
        else:
            result = get_open_prs_formatted()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "stale" in q:
        result = get_stale_prs_formatted()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "open pr" in q or "open pull" in q or "list pr" in q:
        result = get_open_prs_formatted()
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)

    if "ci" in q or "pipeline" in q or "check" in q:
        # Try to extract repo from query
        return QueryResponse(
            status="ok", agent_id=AGENT_ID,
            data="Use GET /ci/status?repo=owner/repo for CI status.",
        )

    if "digest" in q:
        digest = build_pr_digest(profile_id=PROFILE_ID)
        return QueryResponse(status="ok", agent_id=AGENT_ID, data=digest)

    # Default: show all open PRs
    result = get_open_prs_formatted()
    return QueryResponse(status="ok", agent_id=AGENT_ID, data=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
