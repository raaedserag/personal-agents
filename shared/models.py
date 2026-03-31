"""
Shared data models for inter-agent communication.
All agents and the conductor use these to ensure consistent data shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────

class AgentType(str, Enum):
    JIRA = "jira"
    GITHUB = "github"
    PLANNER = "planner"
    RESEARCH = "research"
    INFRA = "infra"


class ProfileScope(str, Enum):
    LEADER = "leader"
    INDIVIDUAL = "individual"
    PERSONAL = "personal"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class TaskType(str, Enum):
    """LLM routing: which model tier to use."""
    DEFAULT = "default"   # Ollama — fast, local
    HEAVY = "heavy"       # Claude API — complex reasoning


# ── Agent Registry ───────────────────────────────────────────────

class AgentInfo(BaseModel):
    """Represents a registered agent in the conductor's registry."""
    id: str                          # e.g., "jira-yassir"
    agent_type: AgentType
    profile_id: str                  # e.g., "yassir"
    url: str                         # e.g., "http://jira-yassir:8000"
    port: int
    health: HealthStatus = HealthStatus.UNHEALTHY
    last_checked: datetime | None = None


# ── Agent Communication ──────────────────────────────────────────

class QueryRequest(BaseModel):
    """Standard request format for agent /query endpoints."""
    query: str
    profile_id: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    """Standard response format from agent /query endpoints."""
    status: str                      # "ok", "error", "unsupported"
    agent_id: str = ""
    data: Any = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Jira Models ──────────────────────────────────────────────────

class TicketSummary(BaseModel):
    """Compact ticket representation for lists and digests."""
    key: str                         # e.g., "ATH-123"
    summary: str
    status: str
    assignee: str = "Unassigned"
    priority: str = "None"
    project: str = ""
    updated: str | None = None


class TicketDetail(TicketSummary):
    """Full ticket representation with description and comments."""
    description: str = ""
    comments: list[TicketComment] = Field(default_factory=list)


class TicketComment(BaseModel):
    author: str
    body: str
    created: str


class StandupData(BaseModel):
    """Structured standup export for the planner agent."""
    profile_id: str
    scope: ProfileScope
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    my_tickets: list[TicketSummary] = Field(default_factory=list)
    blocked_tickets: list[TicketSummary] = Field(default_factory=list)
    # Leader scope only
    team_tickets: list[TicketSummary] = Field(default_factory=list)
    stale_tickets: list[TicketSummary] = Field(default_factory=list)


# ── GitHub Models ────────────────────────────────────────────────

class PRSummary(BaseModel):
    """Compact PR representation."""
    repo: str
    number: int
    title: str
    author: str
    status: str                      # "open", "draft", "merged", "closed"
    reviewers: list[str] = Field(default_factory=list)
    ci_status: str = "unknown"       # "passing", "failing", "pending", "unknown"
    created_at: str | None = None
    updated_at: str | None = None
    url: str = ""


class PRDigest(BaseModel):
    """Aggregated PR data for the planner agent."""
    profile_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    open_prs: list[PRSummary] = Field(default_factory=list)
    review_requested: list[PRSummary] = Field(default_factory=list)
    stale_prs: list[PRSummary] = Field(default_factory=list)


# ── Briefing Models ──────────────────────────────────────────────

class BriefingSection(BaseModel):
    """A section in a morning/EOD briefing."""
    title: str
    icon: str = ""
    items: list[str] = Field(default_factory=list)
    raw_data: Any = None             # structured data for dashboard rendering


class Briefing(BaseModel):
    """Full briefing (morning or EOD)."""
    briefing_type: str               # "morning", "eod", "blockers", "prs"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    sections: list[BriefingSection] = Field(default_factory=list)
    markdown: str = ""               # rendered markdown for CLI display


# ── Memory Models ────────────────────────────────────────────────

class MemoryEntry(BaseModel):
    """A single memory record."""
    id: int | None = None
    agent_id: str
    profile_id: str = ""
    memory_type: str                 # "query_log", "daily_summary", "context"
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


class SharedContext(BaseModel):
    """Cross-agent shared context entry."""
    id: int | None = None
    source_agent: str
    context_type: str                # "blocker", "pr_pending", "incident"
    profile_id: str = ""
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: datetime | None = None
