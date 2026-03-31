"""
Agent Client — HTTP client for inter-agent communication.

Used by the conductor to call agents, and by agents to call each other.
Handles retries, timeouts, and API key injection.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from .models import QueryRequest, QueryResponse


class AgentClient:
    """HTTP client for calling agent APIs."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("AGENT_API_KEY", "")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", self._headers())

        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError:
            return {"status": "error", "error": f"Cannot connect to {url}"}
        except requests.exceptions.Timeout:
            return {"status": "error", "error": f"Timeout connecting to {url}"}
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else "unknown"
            detail = ""
            if e.response is not None:
                try:
                    detail = e.response.json().get("detail", e.response.text[:300])
                except Exception:
                    detail = e.response.text[:300]
            return {"status": "error", "error": f"HTTP {status_code}: {detail}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Standard Agent API ───────────────────────────────────────

    def health(self) -> dict[str, Any]:
        """Check agent health."""
        return self._request("GET", "/health")

    def query(self, query: str, profile_id: str = "",
              context: dict | None = None) -> QueryResponse:
        """Send a natural language query to an agent."""
        req = QueryRequest(query=query, profile_id=profile_id, context=context or {})
        data = self._request("POST", "/query", json=req.model_dump())
        return QueryResponse(**data) if "status" in data else QueryResponse(
            status="error", error=data.get("error", "Unknown error"),
        )

    def get(self, path: str) -> dict[str, Any]:
        """Generic GET request to an agent endpoint."""
        return self._request("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict[str, Any]:
        """Generic POST request to an agent endpoint."""
        return self._request("POST", path, json=body or {})

    # ── Jira Agent Shortcuts ─────────────────────────────────────

    def get_my_tickets(self) -> dict[str, Any]:
        return self._request("GET", "/tickets/mine")

    def get_ticket(self, issue_key: str) -> dict[str, Any]:
        return self._request("GET", f"/tickets/{issue_key}")

    def get_standup_data(self) -> dict[str, Any]:
        return self._request("GET", "/standup-data")

    def get_blocked_tickets(self) -> dict[str, Any]:
        return self._request("GET", "/tickets/blocked")

    # ── GitHub Agent Shortcuts ───────────────────────────────────

    def get_open_prs(self, author: str = "", reviewer: str = "") -> dict[str, Any]:
        params = {}
        if author:
            params["author"] = author
        if reviewer:
            params["reviewer"] = reviewer
        return self._request("GET", "/prs/open", params=params)

    def get_pr_digest(self) -> dict[str, Any]:
        return self._request("GET", "/prs/digest")

    def get_pr_summary(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        return self._request("GET", f"/prs/{owner}/{repo}/{pr_number}/summary")


class AgentRegistry:
    """Manages connections to multiple agents. Used by the conductor."""

    def __init__(self):
        self._clients: dict[str, AgentClient] = {}

    def register(self, agent_id: str, base_url: str, api_key: str | None = None) -> None:
        self._clients[agent_id] = AgentClient(base_url, api_key)

    def get(self, agent_id: str) -> AgentClient | None:
        return self._clients.get(agent_id)

    def get_by_type(self, agent_type: str) -> list[tuple[str, AgentClient]]:
        """Get all agents of a given type (e.g., 'jira', 'github')."""
        return [
            (aid, client) for aid, client in self._clients.items()
            if aid.startswith(agent_type)
        ]

    def get_by_profile(self, profile_id: str) -> list[tuple[str, AgentClient]]:
        """Get all agents for a given profile (e.g., 'yassir')."""
        return [
            (aid, client) for aid, client in self._clients.items()
            if profile_id in aid
        ]

    def health_check_all(self) -> dict[str, dict[str, Any]]:
        """Check health of all registered agents."""
        results = {}
        for agent_id, client in self._clients.items():
            results[agent_id] = client.health()
        return results

    @property
    def agent_ids(self) -> list[str]:
        return list(self._clients.keys())
