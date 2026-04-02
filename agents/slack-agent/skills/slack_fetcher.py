"""
Slack Fetcher — Read-only Slack API interactions using a user token.

Surfaces mentions, important DMs, and channel highlights.
Uses Slack Web API with a user token (xoxp-...).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import requests

SLACK_TOKEN = os.getenv("SLACK_USER_TOKEN", "")
SLACK_BASE = "https://slack.com/api"

# Channels to monitor — comma-separated channel IDs or names
# If empty, fetches from conversations.list
SLACK_CHANNELS = [
    c.strip() for c in os.getenv("SLACK_CHANNELS", "").split(",") if c.strip()
]


def _slack_request(method: str, **params) -> dict:
    """Make a Slack API request."""
    if not SLACK_TOKEN:
        return {"error": "SLACK_USER_TOKEN not configured"}

    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    try:
        resp = requests.get(
            f"{SLACK_BASE}/{method}",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            return {"error": f"Slack API error: {data.get('error', 'unknown')}"}
        return data
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to Slack API"}
    except requests.exceptions.Timeout:
        return {"error": "Slack API request timed out"}
    except Exception as e:
        return {"error": str(e)}


def _get_user_id() -> str | None:
    """Get current user's Slack ID."""
    data = _slack_request("auth.test")
    return data.get("user_id")


def _get_user_name(user_id: str, _cache: dict = {}) -> str:
    """Resolve user ID to display name."""
    if user_id in _cache:
        return _cache[user_id]
    data = _slack_request("users.info", user=user_id)
    name = data.get("user", {}).get("real_name") or data.get("user", {}).get("name", user_id)
    _cache[user_id] = name
    return name


def _get_channel_name(channel_id: str, _cache: dict = {}) -> str:
    """Resolve channel ID to name."""
    if channel_id in _cache:
        return _cache[channel_id]
    data = _slack_request("conversations.info", channel=channel_id)
    name = data.get("channel", {}).get("name", channel_id)
    _cache[channel_id] = name
    return name


def _ts_to_iso(ts: str) -> str:
    """Convert Slack timestamp to ISO format."""
    try:
        return datetime.fromtimestamp(float(ts)).isoformat()
    except (ValueError, TypeError):
        return ts


def get_recent_mentions(hours: int = 24, max_results: int = 15) -> list[dict]:
    """Get messages where you were mentioned or DMed recently."""
    user_id = _get_user_id()
    if not user_id:
        return []

    since = str(time.time() - hours * 3600)

    # Search for mentions
    data = _slack_request(
        "search.messages",
        query=f"<@{user_id}>",
        sort="timestamp",
        sort_dir="desc",
        count=max_results,
    )

    if "error" in data:
        return []

    messages = data.get("messages", {}).get("matches", [])
    results = []
    for msg in messages:
        if float(msg.get("ts", "0")) < float(since):
            continue
        results.append({
            "channel": msg.get("channel", {}).get("name", "unknown"),
            "channel_id": msg.get("channel", {}).get("id", ""),
            "author": msg.get("username", "unknown"),
            "text": msg.get("text", "")[:200],
            "timestamp": _ts_to_iso(msg.get("ts", "")),
            "permalink": msg.get("permalink", ""),
            "type": "mention",
        })

    return results


def get_channel_updates(hours: int = 12, max_per_channel: int = 5) -> list[dict]:
    """Get recent messages from monitored channels."""
    since = str(time.time() - hours * 3600)
    channels = SLACK_CHANNELS

    # If no channels configured, get the user's top channels
    if not channels:
        conv_data = _slack_request(
            "conversations.list",
            types="public_channel,private_channel",
            limit=10,
            exclude_archived="true",
        )
        if "error" not in conv_data:
            channels = [c["id"] for c in conv_data.get("channels", [])[:10]]

    results = []
    for channel_id in channels:
        history = _slack_request(
            "conversations.history",
            channel=channel_id,
            oldest=since,
            limit=max_per_channel,
        )
        if "error" in history:
            continue

        channel_name = _get_channel_name(channel_id)
        for msg in history.get("messages", []):
            if msg.get("subtype") in ("channel_join", "channel_leave", "bot_message"):
                continue
            results.append({
                "channel": channel_name,
                "channel_id": channel_id,
                "author": _get_user_name(msg.get("user", "unknown")),
                "text": msg.get("text", "")[:200],
                "timestamp": _ts_to_iso(msg.get("ts", "")),
                "thread_ts": msg.get("thread_ts"),
                "reply_count": msg.get("reply_count", 0),
                "type": "channel",
            })

    # Sort by timestamp descending
    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results


def get_dm_summary(hours: int = 24, max_results: int = 10) -> list[dict]:
    """Get recent direct messages."""
    since = str(time.time() - hours * 3600)

    # Get DM conversations
    conv_data = _slack_request(
        "conversations.list",
        types="im",
        limit=20,
    )
    if "error" in conv_data:
        return []

    results = []
    for conv in conv_data.get("channels", []):
        channel_id = conv["id"]
        history = _slack_request(
            "conversations.history",
            channel=channel_id,
            oldest=since,
            limit=3,
        )
        if "error" in history:
            continue

        messages = history.get("messages", [])
        if not messages:
            continue

        user_name = _get_user_name(conv.get("user", "unknown"))
        for msg in messages:
            results.append({
                "channel": f"DM: {user_name}",
                "channel_id": channel_id,
                "author": _get_user_name(msg.get("user", "unknown")),
                "text": msg.get("text", "")[:200],
                "timestamp": _ts_to_iso(msg.get("ts", "")),
                "type": "dm",
            })

        if len(results) >= max_results:
            break

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:max_results]


def get_unread_highlights(hours: int = 24) -> dict:
    """Get a combined summary of mentions, important DMs, and active threads."""
    mentions = get_recent_mentions(hours=hours, max_results=10)
    dms = get_dm_summary(hours=hours, max_results=5)
    channels = get_channel_updates(hours=min(hours, 12), max_per_channel=3)

    return {
        "mentions": mentions,
        "direct_messages": dms,
        "channel_highlights": channels[:15],
        "summary": {
            "mention_count": len(mentions),
            "dm_count": len(dms),
            "channel_update_count": len(channels),
        },
    }
