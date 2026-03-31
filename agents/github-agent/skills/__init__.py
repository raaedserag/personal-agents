from .github_fetcher import (
    get_open_prs,
    get_open_prs_formatted,
    get_pr_details,
    get_pr_details_formatted,
    get_pr_diff,
    get_stale_prs,
    get_stale_prs_formatted,
    get_ci_status,
    get_ci_status_formatted,
    get_pr_ci_status,
    check_pr_quality,
    build_pr_digest,
)
from .pr_summarizer import summarize_pr, summarize_pr_formatted

TOOL_REGISTRY = {
    "get_open_prs": get_open_prs,
    "get_open_prs_formatted": get_open_prs_formatted,
    "get_pr_details": get_pr_details,
    "get_pr_details_formatted": get_pr_details_formatted,
    "get_pr_diff": get_pr_diff,
    "get_stale_prs": get_stale_prs,
    "get_stale_prs_formatted": get_stale_prs_formatted,
    "get_ci_status": get_ci_status,
    "get_ci_status_formatted": get_ci_status_formatted,
    "check_pr_quality": check_pr_quality,
    "build_pr_digest": build_pr_digest,
    "summarize_pr": summarize_pr,
    "summarize_pr_formatted": summarize_pr_formatted,
}

WRITE_TOOLS = {"post_review"}  # future: when review posting is added
