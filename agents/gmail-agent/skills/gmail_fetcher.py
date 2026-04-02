"""
Gmail Fetcher — Read-only Gmail API interactions.

Surfaces unread important emails, recent threads needing action.
Uses OAuth tokens managed by shared/google_auth.py.
"""

from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")
from shared.google_auth import google_request

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def get_unread_important(max_results: int = 10) -> list[dict]:
    """Get unread emails marked as important or in primary inbox."""
    data = google_request(
        "GET",
        f"{GMAIL_BASE}/messages",
        params={
            "q": "is:unread category:primary",
            "maxResults": max_results,
        },
    )

    if "error" in data:
        return []

    messages = data.get("messages", [])
    return [_get_message_summary(m["id"]) for m in messages]


def get_recent_threads(hours: int = 24, max_results: int = 10) -> list[dict]:
    """Get recently active email threads."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_str = since.strftime("%Y/%m/%d")

    data = google_request(
        "GET",
        f"{GMAIL_BASE}/messages",
        params={
            "q": f"after:{since_str} category:primary",
            "maxResults": max_results,
        },
    )

    if "error" in data:
        return []

    messages = data.get("messages", [])
    return [_get_message_summary(m["id"]) for m in messages]


def get_action_needed(max_results: int = 10) -> list[dict]:
    """Get emails that likely need a reply or action.

    Heuristic: unread emails where you're in TO (not CC), from a real person
    (not noreply), received in the last 3 days.
    """
    data = google_request(
        "GET",
        f"{GMAIL_BASE}/messages",
        params={
            "q": "is:unread to:me -from:noreply -from:no-reply -from:notifications newer_than:3d category:primary",
            "maxResults": max_results,
        },
    )

    if "error" in data:
        return []

    messages = data.get("messages", [])
    return [_get_message_summary(m["id"]) for m in messages]


def _get_message_summary(message_id: str) -> dict:
    """Fetch a single message and extract summary info."""
    data = google_request(
        "GET",
        f"{GMAIL_BASE}/messages/{message_id}",
        params={"format": "metadata", "metadataHeaders": "From,To,Subject,Date"},
    )

    if "error" in data:
        return {"id": message_id, "error": data["error"]}

    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}

    return {
        "id": message_id,
        "subject": headers.get("Subject", "No subject"),
        "from": headers.get("From", "Unknown"),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "snippet": data.get("snippet", "")[:150],
        "labels": data.get("labelIds", []),
        "is_unread": "UNREAD" in data.get("labelIds", []),
    }
