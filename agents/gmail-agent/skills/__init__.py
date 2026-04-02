from .gmail_fetcher import (
    get_unread_important,
    get_recent_threads,
    get_action_needed,
)

TOOL_REGISTRY = {
    "get_unread_important": get_unread_important,
    "get_recent_threads": get_recent_threads,
    "get_action_needed": get_action_needed,
}
