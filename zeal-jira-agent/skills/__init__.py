from .jira_fetcher import (
    get_my_open_tickets,
    get_team_open_tickets,
    get_ticket_details,
    search_tickets,
    get_blocked_tickets,
    transition_ticket,
    add_comment,
    assign_ticket,
    create_ticket,
)

TOOL_REGISTRY = {
    "get_my_open_tickets": get_my_open_tickets,
    "get_team_open_tickets": get_team_open_tickets,
    "get_ticket_details": get_ticket_details,
    "search_tickets": search_tickets,
    "get_blocked_tickets": get_blocked_tickets,
    "transition_ticket": transition_ticket,
    "add_comment": add_comment,
    "assign_ticket": assign_ticket,
    "create_ticket": create_ticket,
}

WRITE_TOOLS = {"transition_ticket", "add_comment", "assign_ticket", "create_ticket"}
