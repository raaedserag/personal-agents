from .calendar_fetcher import (
    get_today_events,
    get_upcoming_events,
    get_free_slots,
)

TOOL_REGISTRY = {
    "get_today_events": get_today_events,
    "get_upcoming_events": get_upcoming_events,
    "get_free_slots": get_free_slots,
}
