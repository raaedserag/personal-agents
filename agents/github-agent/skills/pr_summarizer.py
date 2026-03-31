"""
PR Summarizer — Uses Claude to generate concise PR summaries from diffs.

This is the "heavy" LLM task for the GitHub agent.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")
from shared.llm_client import get_llm_client

from .github_fetcher import get_pr_details, get_pr_diff

SUMMARIZE_SYSTEM_PROMPT = """You are a concise code review assistant. Given a pull request diff and description, produce a brief summary with:

1. **What changed** — 1-2 sentences on the core change
2. **Why** — the motivation (from PR description or inferred from diff)
3. **Key files** — list the most important files changed (max 5)
4. **Risk areas** — anything that looks risky, breaking, or worth careful review
5. **Test coverage** — whether tests were added/modified

Keep the entire summary under 200 words. Be direct, no filler."""


def summarize_pr(owner: str, repo: str, pr_number: int) -> str:
    """Generate a Claude-powered summary of a PR."""
    pr = get_pr_details(owner, repo, pr_number)
    if "error" in pr:
        return f"Error fetching PR: {pr['error']}"

    diff = get_pr_diff(owner, repo, pr_number)
    if diff.startswith("Error"):
        return diff

    pr_context = (
        f"PR: {pr['repo']}#{pr['number']} — {pr['title']}\n"
        f"Author: {pr['author']}\n"
        f"Description: {pr.get('body', 'No description')}\n\n"
        f"Diff:\n{diff}"
    )

    client = get_llm_client()
    response = client.complete(
        messages=[{"role": "user", "content": pr_context}],
        task_type="heavy",
        system_prompt=SUMMARIZE_SYSTEM_PROMPT,
        max_tokens=1024,
    )

    return response


def summarize_pr_formatted(owner: str, repo: str, pr_number: int) -> str:
    """Get a formatted PR summary."""
    summary = summarize_pr(owner, repo, pr_number)
    return f"## PR Summary: {owner}/{repo}#{pr_number}\n\n{summary}"
