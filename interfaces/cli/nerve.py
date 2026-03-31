#!/usr/bin/env python3
"""
nerve — CLI for Nerve Center.

Usage:
    nerve health              Show all agent health statuses
    nerve agents              List registered agents
    nerve tickets             Show your open tickets (all jobs)
    nerve tickets --job yassir Show tickets for a specific job
    nerve ticket ATH-123      Show ticket details
    nerve blocked             Show blocked tickets
    nerve blocked --job yassir Blocked tickets for a specific job
    nerve standup             Show standup data
    nerve standup --job yassir Standup for a specific job
    nerve briefing blockers   Trigger a blocker briefing
    nerve briefing tickets    Trigger a tickets briefing
    nerve switch <profile>    Switch active job context
    nerve query "..."         Natural language query
    nerve query "..." --job yassir  Query scoped to a job
"""

from __future__ import annotations

import os
import sys

import click
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

console = Console()

CONDUCTOR_URL = os.getenv("NERVE_CONDUCTOR_URL", "http://localhost:9000")


def _request(method: str, path: str, **kwargs) -> dict:
    """Make a request to the conductor."""
    url = f"{CONDUCTOR_URL}{path}"
    try:
        resp = requests.request(method, url, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Cannot connect to conductor at {CONDUCTOR_URL}[/red]")
        console.print("Is the conductor running? Try: docker compose up conductor")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        detail = ""
        if e.response is not None:
            try:
                detail = e.response.json().get("detail", e.response.text[:200])
            except Exception:
                detail = e.response.text[:200]
        console.print(f"[red]HTTP {status}: {detail}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# ── CLI Group ────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Nerve Center — your multi-agent operations hub."""
    if ctx.invoked_subcommand is None:
        console.print(Panel(
            "[bold]Nerve Center[/bold]\n\n"
            "Your multi-agent personal operations platform.\n\n"
            "Run [cyan]nerve --help[/cyan] to see available commands.",
            title="⚡ nerve",
            border_style="cyan",
        ))


# ── Health ───────────────────────────────────────────────────────

@cli.command()
def health():
    """Check health of all services."""
    # Conductor health
    data = _request("GET", "/health")
    console.print(f"[green]✓[/green] Conductor: {data.get('status', '?')} "
                  f"({data.get('agents_registered', 0)} agents registered)")

    # All agent health
    agents_data = _request("GET", "/agents")
    agents = agents_data.get("agents", {})

    if not agents:
        console.print("[yellow]No agents registered.[/yellow]")
        return

    table = Table(title="Agent Health")
    table.add_column("Agent", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("URL", style="dim")

    for agent_id, info in agents.items():
        health_info = info.get("health", {})
        status = health_info.get("status", "unknown")
        if status == "ok":
            status_display = "[green]● healthy[/green]"
        else:
            status_display = f"[red]● {status}[/red]"
        table.add_row(agent_id, status_display, info.get("url", ""))

    console.print(table)


# ── Agents ───────────────────────────────────────────────────────

@cli.command()
def agents():
    """List all registered agents."""
    data = _request("GET", "/agents")
    agents_map = data.get("agents", {})

    if not agents_map:
        console.print("[yellow]No agents registered.[/yellow]")
        return

    table = Table(title="Registered Agents")
    table.add_column("Agent ID", style="cyan")
    table.add_column("Profile", style="magenta")
    table.add_column("Scope")
    table.add_column("Status", justify="center")

    for agent_id, info in agents_map.items():
        health_info = info.get("health", {})
        status = health_info.get("status", "unknown")
        profile = health_info.get("profile", "?")
        scope = health_info.get("scope", "?")
        status_display = "[green]●[/green]" if status == "ok" else "[red]●[/red]"
        table.add_row(agent_id, profile, scope, status_display)

    console.print(table)


# ── Tickets ──────────────────────────────────────────────────────

@cli.command()
@click.option("--job", "-j", default="", help="Filter by job profile (e.g., yassir, zeal)")
def tickets(job: str):
    """Show your open tickets."""
    data = _request("GET", "/briefing/tickets", params={"profile_id": job} if job else {})
    ticket_data = data.get("data", {})

    if not ticket_data:
        console.print("[yellow]No ticket data returned.[/yellow]")
        return

    for agent_id, result in ticket_data.items():
        profile = agent_id.replace("jira-", "")
        console.print(f"\n[bold cyan]── {profile.upper()} ──[/bold cyan]")

        if isinstance(result, dict) and result.get("status") == "ok":
            content = result.get("data", "")
            if isinstance(content, str):
                console.print(content)
            else:
                console.print(str(content))
        elif isinstance(result, dict) and "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
        else:
            console.print(str(result))


# ── Ticket Detail ────────────────────────────────────────────────

@cli.command()
@click.argument("issue_key")
def ticket(issue_key: str):
    """Show details for a specific ticket (e.g., nerve ticket ATH-123)."""
    # Determine which agent to query based on project key prefix
    data = _request("POST", "/query", json={
        "query": f"get ticket details {issue_key}",
    })

    results = data.get("results", {})
    if not results:
        console.print(f"[yellow]No agent could find ticket {issue_key}.[/yellow]")
        return

    for agent_id, result in results.items():
        if isinstance(result, dict):
            content = result.get("data", "")
            if content:
                console.print(Panel(str(content), title=f"[cyan]{issue_key}[/cyan]", border_style="blue"))


# ── Blocked ──────────────────────────────────────────────────────

@cli.command()
@click.option("--job", "-j", default="", help="Filter by job profile")
def blocked(job: str):
    """Show blocked tickets."""
    data = _request("GET", "/briefing/blockers", params={"profile_id": job} if job else {})
    blocker_data = data.get("data", {})

    if not blocker_data:
        console.print("[green]No blocked tickets found.[/green]")
        return

    for agent_id, result in blocker_data.items():
        profile = agent_id.replace("jira-", "")
        console.print(f"\n[bold red]── BLOCKERS: {profile.upper()} ──[/bold red]")

        if isinstance(result, dict) and result.get("status") == "ok":
            content = result.get("data", "")
            console.print(str(content))
        elif isinstance(result, dict) and "error" in result:
            console.print(f"[red]Error: {result['error']}[/red]")
        else:
            console.print(str(result))


# ── Standup ──────────────────────────────────────────────────────

@cli.command()
@click.option("--job", "-j", default="", help="Filter by job profile")
def standup(job: str):
    """Show standup data."""
    data = _request("POST", "/query", json={
        "query": "standup data",
        "profile_id": job,
    })

    results = data.get("results", {})
    if not results:
        console.print("[yellow]No standup data available.[/yellow]")
        return

    for agent_id, result in results.items():
        profile = agent_id.replace("jira-", "")
        console.print(f"\n[bold magenta]── STANDUP: {profile.upper()} ──[/bold magenta]")
        if isinstance(result, dict):
            content = result.get("data", result)
            if isinstance(content, dict) and "my_tickets" in content:
                _render_standup(content, profile)
            else:
                console.print(str(content))
        else:
            console.print(str(result))


def _render_standup(data: dict, profile: str):
    """Render structured standup data as a table."""
    my_tickets = data.get("my_tickets", [])
    blocked = data.get("blocked_tickets", [])
    stale = data.get("stale_tickets", [])

    if my_tickets:
        table = Table(title="Your Open Tickets")
        table.add_column("Key", style="cyan")
        table.add_column("Summary")
        table.add_column("Status", style="yellow")
        table.add_column("Priority")
        for t in my_tickets[:10]:
            table.add_row(t["key"], t["summary"][:60], t["status"], t["priority"])
        console.print(table)

    if blocked:
        console.print(f"\n[red]Blocked ({len(blocked)}):[/red]")
        for t in blocked:
            console.print(f"  [red]●[/red] [{t['key']}] {t['summary'][:60]} — {t['assignee']}")

    if stale:
        console.print(f"\n[yellow]Stale ({len(stale)}):[/yellow]")
        for t in stale[:5]:
            console.print(f"  [yellow]●[/yellow] [{t['key']}] {t['summary'][:60]} — {t['assignee']}")


# ── Briefing ─────────────────────────────────────────────────────

@cli.command()
@click.argument("briefing_type", type=click.Choice(["blockers", "tickets"]))
@click.option("--job", "-j", default="", help="Filter by job profile")
def briefing(briefing_type: str, job: str):
    """Trigger a briefing (blockers, tickets)."""
    params = {"profile_id": job} if job else {}
    data = _request("GET", f"/briefing/{briefing_type}", params=params)
    console.print(Panel(
        str(data.get("data", data)),
        title=f"[bold]Briefing: {briefing_type}[/bold]",
        border_style="cyan",
    ))


# ── Context Switch ───────────────────────────────────────────────

@cli.command()
@click.argument("profile_id")
def switch(profile_id: str):
    """Switch active job context."""
    data = _request("GET", f"/context/{profile_id}")

    console.print(f"\n[bold green]Switched to: {profile_id.upper()}[/bold green]")

    agents_info = data.get("agents", {})
    for agent_id, info in agents_info.items():
        status = info.get("health", "unknown")
        icon = "[green]●[/green]" if status == "ok" else "[red]●[/red]"
        console.print(f"  {icon} {agent_id}")

    console.print(f"\n[dim]Context loaded at {data.get('loaded_at', '?')}[/dim]")


# ── Natural Language Query ───────────────────────────────────────

@cli.command()
@click.argument("query_text")
@click.option("--job", "-j", default="", help="Scope query to a job profile")
def query(query_text: str, job: str):
    """Ask a natural language question."""
    data = _request("POST", "/query", json={
        "query": query_text,
        "profile_id": job,
    })

    routed = data.get("routed_to", {})
    if routed:
        agents_list = []
        for targets in routed.values():
            agents_list.extend(targets)
        console.print(f"[dim]Routed to: {', '.join(agents_list)}[/dim]\n")

    results = data.get("results", {})
    if not results:
        error = data.get("error", "No results.")
        console.print(f"[yellow]{error}[/yellow]")
        return

    for agent_id, result in results.items():
        if isinstance(result, dict):
            status = result.get("status", "?")
            content = result.get("data", "")
            error = result.get("error", "")
            if error:
                console.print(f"[red]{agent_id}: {error}[/red]")
            elif content:
                console.print(Panel(str(content), title=f"[cyan]{agent_id}[/cyan]", border_style="blue"))
        else:
            console.print(f"{agent_id}: {result}")


# ── Entry Point ──────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
