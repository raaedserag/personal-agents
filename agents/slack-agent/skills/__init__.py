from .slack_fetcher import (
    get_recent_mentions,
    get_channel_updates,
    get_dm_summary,
    get_unread_highlights,
)

TOOL_REGISTRY = {
    "get_recent_mentions": get_recent_mentions,
    "get_channel_updates": get_channel_updates,
    "get_dm_summary": get_dm_summary,
    "get_unread_highlights": get_unread_highlights,
}
