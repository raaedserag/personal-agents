from .briefing_builder import (
    build_morning_briefing,
    build_eod_summary,
    build_blocker_alert,
    build_pr_digest,
)
from .blocker_monitor import check_blockers

TOOL_REGISTRY = {
    "build_morning_briefing": build_morning_briefing,
    "build_eod_summary": build_eod_summary,
    "build_blocker_alert": build_blocker_alert,
    "build_pr_digest": build_pr_digest,
    "check_blockers": check_blockers,
}
