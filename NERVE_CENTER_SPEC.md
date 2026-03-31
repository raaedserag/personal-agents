# Nerve Center — Multi-Agent Personal Operations Platform

## System Spec v1.0

---

## 1. Vision

Nerve Center is a self-hosted, Docker-based multi-agent system that acts as a unified command layer across your professional and personal life. Each agent is a specialized microservice with its own identity, tools, memory, and LLM configuration. A thin conductor service orchestrates cross-agent queries, scheduled reports, and the web dashboard.

**Design principles:**

- **Job isolation**: Each job gets its own agent instances with separate credentials, memory, and context. No data leaks between jobs.
- **Agent composability**: Agents expose standard APIs. Any agent can query any other agent. The conductor fans out and aggregates.
- **LLM flexibility**: Each agent declares which tasks need local (Ollama) vs cloud (Claude API) inference. Cost-sensitive by default.
- **Iterative build**: Start with conductor + 2 agents, add more over time. Every agent follows the same scaffold pattern.

---

## 2. Job Profiles

The system supports named job profiles. Each profile encapsulates credentials, team info, and tool configurations for one work context.

```yaml
# profiles/zeal.yaml
profile_id: zeal
label: "Zeal — Cloud/Platform/SRE Lead"
role: "Cloud Team Lead / DevOps / SRE"
scope: "leader"                          # agent behavior: proactive, team-wide
team_size: 4                             # teams you coordinate with
apps_maintained: 50+
team_members:                            # hardcoded for followup engine
  - name: "TBD"                          # fill in your team members
    email: "member1@getzeal.io"
    role: "backend"
  # ... add all team members
integrations:
  jira:
    domain: "https://zeal.atlassian.net"
    email: "${ZEAL_JIRA_EMAIL}"
    api_token: "${ZEAL_JIRA_TOKEN}"
    projects: [ATH, ATHSP, ATL, ATLSP, HRM, HRMSP, APL, APLSP, CL]
  github:
    org: "zeal-org"                      # replace with actual org
    token: "${ZEAL_GITHUB_TOKEN}"
    repos: []                            # empty = all repos in org
  slack:
    workspace: "zeal-workspace"
    bot_token: "${ZEAL_SLACK_BOT_TOKEN}"
  pagerduty:
    api_key: "${ZEAL_PD_API_KEY}"
    service_ids: []                      # fill in monitored services
  aws:
    region: "${ZEAL_AWS_REGION}"
    # ECS, Elasticsearch, Grafana monitoring
    services: [ecs, elasticsearch, grafana]
  google_workspace:
    enabled: true
  calendar:
    provider: "google"
    calendar_id: "primary"

# profiles/yassir.yaml
profile_id: yassir
label: "Yassir — Software Engineer"
role: "Software Engineer (IC)"
scope: "individual"                      # agent behavior: reactive, personal focus
integrations:
  jira:
    domain: "https://yassir.atlassian.net"   # replace with actual domain
    email: "${YASSIR_JIRA_EMAIL}"
    api_token: "${YASSIR_JIRA_TOKEN}"
    projects: []                         # fill in your project keys
  github:
    org: "yassir-org"                    # replace with actual org
    token: "${YASSIR_GITHUB_TOKEN}"
    repos: []                            # fill in your active repos
  slack:
    workspace: "yassir-workspace"
    bot_token: "${YASSIR_SLACK_BOT_TOKEN}"
  gcp:
    project_id: "${YASSIR_GCP_PROJECT}"
    # GKE access for debugging
    services: [gke]
  # mongodb: read-only access for debugging queries
  # datadog: optional, rarely used
  # notion: optional, for docs reference

# profiles/freelance.yaml
profile_id: freelance
label: "Freelance Projects"
role: "Consultant / Contractor"
scope: "individual"
integrations:
  github:
    token: "${FREELANCE_GITHUB_TOKEN}"
    repos: []                            # add per-client repos as needed
  # minimal integrations, expanded per project

# profiles/personal.yaml
profile_id: personal
label: "Personal"
scope: "personal"
integrations:
  calendar:
    provider: "google"
    calendar_id: "primary"
  email:
    provider: "gmail"
    address: "${PERSONAL_EMAIL}"
```

**Key distinction — the `scope` field** drives agent behavior:
- `"leader"` (Zeal): Agents are proactive — surface team blockers, chase stale tickets across 4 teams, monitor infra health, generate team-wide reports
- `"individual"` (Yassir, Freelance): Agents are reactive — focus on your tickets, your PRs, fast context switching, get out of your way
- `"personal"`: Minimal — calendar, email, research on demand

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                      INTERFACES                               │
│  ┌──────────────┐   ┌────────────────────────────────────┐   │
│  │  CLI (nerve)  │   │  Web Dashboard (React, PIN auth)   │   │
│  └──────┬───────┘   └────────────────┬───────────────────┘   │
│         └──────────┬─────────────────┘                        │
│                    ▼                                           │
│  ┌──────────────────────────────────┐                         │
│  │          CONDUCTOR               │  Port 9000              │
│  │  - API gateway / router          │                         │
│  │  - Scheduled jobs (cron)         │                         │
│  │  - Agent registry                │                         │
│  │  - Report aggregator             │                         │
│  │  - Dashboard delivery            │                         │
│  └──────┬───────────────────────────┘                         │
│         │  HTTP calls to agent APIs                           │
│  ┌──────┴────────────────────────────────────────────────┐    │
│  │                 AGENT LAYER                            │    │
│  │                                                        │    │
│  │  ┌──────────────┐  ┌──────────────┐                    │    │
│  │  │ jira-agent    │  │ jira-agent    │                   │    │
│  │  │ (zeal)        │  │ (yassir)      │                   │    │
│  │  │ scope:leader  │  │ scope:IC      │                   │    │
│  │  │ Port 20000    │  │ Port 20001    │                   │    │
│  │  └──────────────┘  └──────────────┘                    │    │
│  │                                                        │    │
│  │  ┌──────────────┐  ┌──────────────┐                    │    │
│  │  │ github-agent  │  │ github-agent  │                   │    │
│  │  │ (zeal)        │  │ (yassir)      │                   │    │
│  │  │ Port 20010    │  │ Port 20011    │                   │    │
│  │  └──────────────┘  └──────────────┘                    │    │
│  │                                                        │    │
│  │  ┌──────────────┐  ┌──────────────┐                    │    │
│  │  │ planner-agent│  │research-agent │                   │    │
│  │  │ (global)     │  │ (on-demand)   │                   │    │
│  │  │ Port 20020   │  │ Port 20030    │                   │    │
│  │  └──────────────┘  └──────────────┘                    │    │
│  │                                                        │    │
│  │  ┌──────────────┐                                      │    │
│  │  │ infra-agent   │  ← Zeal only (AWS/ECS/Grafana)      │    │
│  │  │ (zeal)        │                                     │    │
│  │  │ Port 20040    │                                     │    │
│  │  └──────────────┘                                      │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                SHARED SERVICES                          │    │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │  Ollama   │  │   SQLite     │  │  Redis (Phase 2) │  │    │
│  │  │  (LLM)   │  │  (memory)    │  │  (cache/pubsub)  │  │    │
│  │  └──────────┘  └──────────────┘  └──────────────────┘  │    │
│  └────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Agent Inventory

### 4.1 Jira Agent (per job profile)

**Instances:** `jira-zeal` (scope: leader) and `jira-yassir` (scope: individual)  
**Base:** Your existing `zeal-jira-agent`, generalized  
**LLM tier:** Local (Ollama) for tool routing, Cloud (Claude) for summary generation  

**Scope-driven behavior:**

When `scope: leader` (Zeal):
- All existing read/write operations from your current agent
- **Team followup engine** — tracks stale tickets (no update in N days) across 4+ teams, generates nudge drafts per team member from hardcoded roster
- **Cross-project visibility** — monitors all 9 projects (ATH, ATHSP, ATL, ATLSP, HRM, HRMSP, APL, APLSP, CL)
- **Sprint velocity tracking** — stores sprint completion data in memory, surfaces trends
- **Standup data export** — structured endpoint that the planner agent calls to build standup reports
- **Team standup generator** — aggregates what each team member worked on, what's blocked

When `scope: individual` (Yassir):
- Focus on YOUR tickets only — assigned to you, created by you
- PR-linked ticket tracking — when a PR is merged, suggest transitioning the linked ticket
- Simple standup data — what you did yesterday, what you're doing today, blockers

**API surface:**
```
GET  /health
GET  /tickets/mine
GET  /tickets/team?stale_days=3
GET  /tickets/{issue_key}
GET  /tickets/blocked
GET  /standup-data          ← NEW: structured data for planner
POST /query
POST /tickets/transition    ← write, requires confirmation
POST /tickets/comment       ← write, requires confirmation
POST /tickets/assign        ← write, requires confirmation
POST /tickets/create        ← write, requires confirmation
```

### 4.2 GitHub Agent (per job profile)

**Instances:** One per job that uses GitHub  
**LLM tier:** Cloud (Claude) for PR analysis, Local for simple queries  

**Capabilities:**
- List open PRs across configured repos, filtered by author/reviewer/status
- PR summarizer — reads diff, generates a concise summary of what changed and why
- Review quality check — flags PRs with no description, no tests, huge diffs
- Stale PR detection — PRs open > N days with no activity
- CI status aggregation — surfaces failing checks across repos
- Code review draft — generates review comments on a PR (write operation, requires confirmation)

**API surface:**
```
GET  /health
GET  /prs/open?author=&reviewer=&repo=
GET  /prs/{owner}/{repo}/{pr_number}
GET  /prs/{owner}/{repo}/{pr_number}/summary    ← Claude-powered
GET  /prs/stale?days=5
GET  /prs/digest                                 ← for planner
GET  /ci/status?repo=
POST /prs/{owner}/{repo}/{pr_number}/review      ← write
POST /query
```

**Tools:**
- `list_open_prs(repo, author, reviewer)` — GitHub API
- `get_pr_diff(owner, repo, pr_number)` — GitHub API
- `get_pr_details(owner, repo, pr_number)` — GitHub API
- `get_ci_status(owner, repo, ref)` — GitHub API
- `post_review(owner, repo, pr_number, body, comments)` — write tool
- `summarize_pr(diff, pr_description)` — Claude API call

### 4.3 Planner Agent (global, cross-job)

**Instances:** One (accesses all job profiles)  
**LLM tier:** Cloud (Claude) — this agent does heavy synthesis  

**This is your "daily brain."** It calls other agents, aggregates, and produces actionable reports.

**Capabilities:**
- **Morning briefing**: Fans out to all jira-agents (`/standup-data`), github-agents (`/prs/digest`), infra-agent (`/status`), calendar, and PagerDuty to produce a single prioritized daily plan
- **End-of-day summary**: Compares morning plan vs actual activity, highlights carryover
- **Blocker alerts**: Polls jira-agents, infra-agent, and PagerDuty on a schedule, pushes to dashboard
- **PR digest**: Aggregates from all github-agents
- **Context switcher**: When you say "nerve switch zeal", it loads that job's context, recent memory, and active tickets into your CLI/dashboard

**Report templates:**

```markdown
## Morning Briefing — Monday, March 31

### 🔴 Blockers & Incidents (3)
- [ATH-445] Payment gateway timeout — blocked 2 days, assigned: Ahmed
- PagerDuty: 1 open incident (P2, ECS service unhealthy — payments-api)
- [YAS-122] MongoDB query timeout on user-service — you, since Friday

### 📋 Your Tickets Today (across all jobs)
| Job     | Key       | Summary                        | Status      | Priority |
|---------|-----------|--------------------------------|-------------|----------|
| Zeal    | ATH-501   | ECS task def update for auth   | In Progress | High     |
| Zeal    | CL-89     | Grafana alert rules for ELK    | Open        | Medium   |
| Yassir  | YAS-122   | Fix MongoDB query timeout      | In Progress | High     |
| Yassir  | YAS-130   | Implement checkout flow v2     | Open        | Medium   |

### 🏗 Zeal Infra Health
- ECS: 48/50 services healthy (2 degraded: payments-api, notification-svc)
- Elasticsearch: cluster yellow (1 unassigned shard)
- PagerDuty: 1 open, 2 resolved in last 24h

### 🔀 PRs Needing Your Attention (4)
- zeal-org/infra #87 — "ECS autoscaling policy update" — your PR, awaiting review
- zeal-org/api #342 — "Add rate limiting middleware" — awaiting your review (2 days)
- yassir-org/user-service #55 — "Fix N+1 query on /users" — your PR, CI passing
- yassir-org/checkout #18 — "Checkout flow v2" — draft, WIP

### 📅 Calendar
- 10:00 — Zeal standup (Zoom)
- 11:30 — Zeal security team sync
- 14:00 — Yassir sprint planning
- 16:00 — Free block (deep work)

### 📌 Suggested Focus Order
1. Check ECS degraded services (payments-api) — infra incident, high impact
2. Fix YAS-122 MongoDB timeout — in progress, been 3 days
3. Review zeal-org/api #342 — team is waiting
4. Continue ATH-501 ECS task def — in progress
```

**API surface:**
```
GET  /health
GET  /briefing/morning
GET  /briefing/eod
GET  /briefing/blockers
GET  /briefing/prs
GET  /context/{profile_id}       ← load a job's context
POST /query                      ← natural language queries
```

### 4.4 Infra Agent (Zeal only)

**Instances:** One (Zeal profile only)  
**LLM tier:** Local (Ollama) for status checks, Cloud (Claude) for incident analysis  

**This agent exists because Zeal is your SRE/platform role.** It monitors the infrastructure you maintain and surfaces problems before they become pages.

**Capabilities:**
- **ECS health check** — polls AWS ECS for service status across 50+ apps, surfaces unhealthy/degraded services
- **Elasticsearch cluster health** — checks cluster status, unassigned shards, disk usage
- **Grafana alert status** — pulls active/firing alerts from Grafana API
- **PagerDuty integration** — fetches open incidents, recent resolutions, on-call schedule
- **Incident context builder** — when an incident is active, aggregates ECS logs, recent deployments, and related Jira tickets into a single brief

**API surface:**
```
GET  /health
GET  /status                     ← overall infra health summary
GET  /ecs/services               ← ECS service health
GET  /elasticsearch/health       ← ES cluster status
GET  /grafana/alerts             ← active Grafana alerts
GET  /pagerduty/incidents        ← open PD incidents
GET  /pagerduty/oncall           ← who's on call
GET  /incident/{incident_id}     ← full incident context brief
POST /query
```

**Tools:**
- `get_ecs_services(cluster)` — AWS SDK (boto3)
- `get_es_health(endpoint)` — Elasticsearch REST API
- `get_grafana_alerts(api_url, api_key)` — Grafana API
- `get_pd_incidents(api_key)` — PagerDuty API
- `get_pd_oncall(api_key, schedule_id)` — PagerDuty API
- `get_recent_deployments(cluster, hours)` — AWS ECS + CloudTrail
- `build_incident_brief(incident_id)` — Claude-powered synthesis

### 4.5 Research Agent (on-demand)

**Instances:** One  
**LLM tier:** Cloud (Claude) with web search tool  

**Capabilities:**
- **Task-scoped research**: When you're working on a ticket or task that needs research (e.g., "best practices for EKS node group autoscaling"), this agent does deep search and returns a structured brief
- **Feed monitoring**: Tracks configured RSS/news feeds for specific topics, produces periodic digests
- **Personal research**: Investment research, productivity tools — on-demand, not continuous

**Scoping rule:** This agent only activates when explicitly asked or when another agent flags a task that needs research context. It does not run autonomously — you control the scope.

**Topics configuration:**
```yaml
research_topics:
  work:
    - label: "Cloud/DevOps"
      keywords: ["kubernetes", "terraform", "aws", "gcp", "ci/cd", "platform engineering"]
      feeds: ["https://aws.amazon.com/blogs/devops/feed/", ...]
    - label: "Security"
      keywords: ["CVE", "supply chain", "zero trust"]
  personal:
    - label: "Investing"
      keywords: ["etf", "index funds", "macro"]
      on_demand_only: true
```

**API surface:**
```
GET  /health
POST /research                   ← {topic, context, depth: "quick"|"deep"}
GET  /digest?topic=devops        ← latest digest for a topic
POST /query
```

---

## 5. Conductor Service

The conductor is the central nervous system — lightweight, no LLM of its own (it delegates all reasoning to agents).

**Responsibilities:**
1. **Agent registry**: Knows which agents exist, their URLs, health status, and job profile associations
2. **Request routing**: CLI/dashboard sends natural language → conductor parses intent → fans out to relevant agents
3. **Scheduled jobs**: Cron-based triggers for morning briefing, blocker checks, EOD summary
4. **Report aggregation**: Calls multiple agents in parallel, merges results into unified reports
5. **API gateway**: Single entry point for CLI and dashboard

**Configuration:**
```yaml
# conductor/config.yaml
agents:
  - id: jira-zeal
    type: jira
    profile: zeal
    url: http://jira-zeal:8000
    port: 20000

  - id: jira-yassir
    type: jira
    profile: yassir
    url: http://jira-yassir:8000
    port: 20001

  - id: github-zeal
    type: github
    profile: zeal
    url: http://github-zeal:8000
    port: 20010

  - id: github-yassir
    type: github
    profile: yassir
    url: http://github-yassir:8000
    port: 20011

  - id: planner
    type: planner
    profile: global
    url: http://planner:8000
    port: 20020

  - id: research
    type: research
    profile: global
    url: http://research:8000
    port: 20030

  - id: infra-zeal
    type: infra
    profile: zeal
    url: http://infra-zeal:8000
    port: 20040

schedules:
  morning_briefing:
    cron: "0 7 * * 1-5"          # 7 AM weekdays
    action: planner.morning_briefing
    deliver_to: [dashboard]

  blocker_check:
    cron: "0 */3 * * 1-5"        # Every 3 hours on weekdays
    action: planner.blocker_alert
    deliver_to: [dashboard]

  pr_digest:
    cron: "0 9,14 * * 1-5"       # 9 AM and 2 PM
    action: planner.pr_digest
    deliver_to: [dashboard]

  eod_summary:
    cron: "0 18 * * 1-5"         # 6 PM weekdays
    action: planner.eod_summary
    deliver_to: [dashboard]
```

**API surface (what CLI and dashboard call):**
```
GET  /health
GET  /agents                      ← list all agents + health
GET  /briefing/{type}             ← morning, eod, blockers, prs
GET  /context/{profile_id}        ← switch job context
POST /query                       ← natural language → routed to agents
GET  /reports/latest              ← last generated reports
WS   /ws/events                   ← real-time event stream for dashboard
```

---

## 6. Shared Infrastructure

### 6.1 LLM Router

Each agent declares LLM needs per task type in its `agent.yaml`:

```yaml
model:
  default:
    provider: ollama
    name: llama3.2
    base_url: http://ollama:11434
  heavy:
    provider: anthropic
    name: claude-sonnet-4-20250514
    # API key from shared secrets
```

A shared `llm_client` library handles routing:
```python
from shared.llm_client import complete

# Automatically routes based on agent config
response = complete(
    task_type="heavy",      # or "default"
    messages=[...],
    agent_id="github-zeal"
)
```

### 6.2 Memory Store

**Upgrade from file-based to SQLite** (single file, zero ops, Docker-friendly):

```sql
-- Per-agent memory
CREATE TABLE agent_memory (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    profile_id TEXT,
    memory_type TEXT,          -- 'query_log', 'daily_summary', 'context'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP       -- optional TTL
);

-- Cross-agent shared context (what the conductor uses)
CREATE TABLE shared_context (
    id INTEGER PRIMARY KEY,
    source_agent TEXT NOT NULL,
    context_type TEXT,          -- 'blocker', 'pr_pending', 'incident'
    profile_id TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
```

### 6.3 Secrets Management

```
/secrets
  /zeal.env              ← Jira, GitHub, Slack, PagerDuty, AWS creds
  /yassir.env            ← Jira, GitHub, Slack, GCP creds
  /freelance.env         ← GitHub token
  /personal.env          ← Google Calendar, email
  /shared.env            ← ANTHROPIC_API_KEY, DASHBOARD_PIN, shared tokens
```

Docker Compose maps each agent to its profile's env file + shared.env.

### 6.4 Redis (Optional, Phase 2)

For real-time features:
- Pub/sub for blocker alerts → dashboard WebSocket
- Cache layer for repeated Jira/GitHub queries
- Rate limiting for API calls

---

## 7. Repository Structure

```
nerve-center/
├── docker-compose.yml              ← all services
├── profiles/                       ← job profile configs
│   ├── zeal.yaml
│   ├── yassir.yaml
│   ├── freelance.yaml
│   └── personal.yaml
├── secrets/                        ← .gitignored env files
│   ├── zeal.env
│   ├── yassir.env
│   ├── freelance.env
│   ├── personal.env
│   └── shared.env
│
├── conductor/                      ← orchestrator service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                     ← FastAPI app
│   ├── config.yaml                 ← agent registry + schedules
│   ├── router.py                   ← intent → agent routing
│   ├── scheduler.py                ← cron job runner
│   ├── aggregator.py               ← multi-agent response merger
│   └── websocket.py                ← real-time event stream
│
├── agents/
│   ├── _template/                  ← scaffold for new agents
│   │   ├── Dockerfile
│   │   ├── SOUL.md
│   │   ├── DUTIES.md
│   │   ├── agent.yaml
│   │   ├── api.py
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── skills/
│   │       └── __init__.py
│   │
│   ├── jira-agent/                 ← generalized from your existing code
│   │   ├── Dockerfile
│   │   ├── SOUL.md
│   │   ├── DUTIES.md
│   │   ├── agent.yaml
│   │   ├── api.py
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── skills/
│   │       ├── __init__.py
│   │       └── jira_fetcher.py
│   │
│   ├── github-agent/
│   │   ├── Dockerfile
│   │   ├── SOUL.md
│   │   ├── DUTIES.md
│   │   ├── agent.yaml
│   │   ├── api.py
│   │   ├── requirements.txt
│   │   └── skills/
│   │       ├── __init__.py
│   │       ├── pr_fetcher.py
│   │       ├── pr_summarizer.py
│   │       └── ci_checker.py
│   │
│   ├── planner-agent/
│   │   ├── Dockerfile
│   │   ├── SOUL.md
│   │   ├── DUTIES.md
│   │   ├── agent.yaml
│   │   ├── api.py
│   │   ├── requirements.txt
│   │   └── skills/
│   │       ├── __init__.py
│   │       ├── briefing_builder.py
│   │       ├── blocker_monitor.py
│   │       └── calendar_fetcher.py
│   │
│   ├── research-agent/
│       ├── Dockerfile
│       ├── SOUL.md
│       ├── DUTIES.md
│       ├── agent.yaml
│       ├── api.py
│       ├── requirements.txt
│       └── skills/
│           ├── __init__.py
│           ├── web_searcher.py
│           └── feed_monitor.py
│
│   └── infra-agent/                ← Zeal only
│       ├── Dockerfile
│       ├── SOUL.md
│       ├── DUTIES.md
│       ├── agent.yaml
│       ├── api.py
│       ├── requirements.txt
│       └── skills/
│           ├── __init__.py
│           ├── ecs_monitor.py
│           ├── es_monitor.py
│           ├── grafana_client.py
│           └── pagerduty_client.py
│
├── shared/                         ← shared Python package
│   ├── __init__.py
│   ├── llm_client.py              ← LLM routing (ollama vs claude)
│   ├── memory.py                  ← SQLite memory client
│   ├── auth.py                    ← API key verification + dashboard PIN
│   ├── models.py                  ← shared Pydantic models
│   └── agent_client.py            ← HTTP client for agent-to-agent calls
│
├── interfaces/
│   ├── cli/
│   │   ├── requirements.txt
│   │   └── nerve.py               ← Rich CLI app ("nerve" command)
│   │
│   └── dashboard/
│       ├── Dockerfile
│       ├── package.json
│       ├── src/
│       │   ├── App.jsx
│       │   ├── components/
│       │   │   ├── LoginScreen.jsx     ← PIN auth
│       │   │   ├── JobTabs.jsx         ← Zeal | Yassir | Freelance tabs
│       │   │   ├── BriefingPanel.jsx
│       │   │   ├── TicketList.jsx
│       │   │   ├── PRDigest.jsx
│       │   │   ├── BlockerAlerts.jsx
│       │   │   ├── InfraHealth.jsx     ← Zeal tab only
│       │   │   └── AgentHealth.jsx
│       │   └── hooks/
│       │       └── useWebSocket.js
│       └── vite.config.js
│
├── data/                           ← Docker volumes mount here
│   ├── memory.db                  ← SQLite
│   └── ollama/                    ← Ollama model cache
│
└── scripts/
    ├── setup.sh                   ← first-time setup wizard
    ├── new-agent.sh               ← scaffold a new agent from _template
    └── new-profile.sh             ← create a new job profile
```

---

## 8. Build Plan — Phase 1

**Goal:** Working conductor + jira-agent + github-agent for your primary job. Morning briefing and PR digest functional via CLI.

### Sprint 1 (Week 1): Foundation
- [ ] Set up monorepo structure from section 7
- [ ] Build `shared/` package (llm_client, memory, auth, models)
- [ ] Generalize existing jira-agent to accept profile config
- [ ] Create conductor with agent registry and health checks
- [ ] CLI skeleton that talks to conductor

### Sprint 2 (Week 2): GitHub Agent + Reports
- [ ] Build github-agent with PR listing + summarization
- [ ] Implement conductor's aggregator for multi-agent responses
- [ ] Build morning briefing (jira data + PR data)
- [ ] Build blocker alert endpoint

### Sprint 3 (Week 3): Second Job Profile + Scheduling
- [ ] Add second job profile (duplicate jira + github agents)
- [ ] Implement conductor's scheduler (cron-based reports)
- [ ] Build EOD summary
- [ ] PR digest as scheduled report

### Sprint 4 (Week 4): Dashboard MVP
- [ ] React dashboard with job tabs
- [ ] Briefing panel (morning/EOD)
- [ ] Ticket list + PR digest panels
- [ ] WebSocket for live updates

### Phase 2 (Future):
- Infra agent (Zeal — AWS/ECS/Grafana/PagerDuty monitoring)
- Planner agent with Google Calendar integration
- Research agent
- Redis for pub/sub + caching
- Slack bot interface (Phase 3)
- Mobile-friendly dashboard

---

## 9. Key Design Decisions

### Why microservices over a monolith?
Your jobs have different security boundaries. Zeal credentials must never be accessible to Yassir agents. Docker network isolation gives you this for free. It also means you can restart one agent without affecting others.

### Why SQLite over Postgres?
For a single-user local system, SQLite is zero-ops and handles the concurrency you'll have (a few agents writing occasionally). If you later move to a VPS with multiple users, swap to Postgres — the shared memory client abstracts this.

### Why conductor doesn't have its own LLM?
The conductor is a router, not a thinker. It uses simple keyword/intent matching to route requests. Agents do the reasoning. This keeps the conductor fast and reliable — if an LLM is down, only the affected agent is impacted, not the routing layer.

### Why SOUL.md + DUTIES.md per agent?
You already established this pattern and it's excellent. SOUL defines *who* the agent is (tone, expertise, constraints). DUTIES defines *what* it can do (permissions, boundaries). Separating them means you can swap duties without changing identity, and vice versa.

### Why not a shared message bus from day 1?
YAGNI. HTTP calls between agents are simple, debuggable, and sufficient for your scale. Redis pub/sub in Phase 2 adds real-time capabilities when the dashboard needs live updates. Starting with HTTP keeps Phase 1 lean.

### Why a separate infra-agent instead of adding AWS tools to the Jira agent?
Separation of concerns. The Jira agent is about project management. The infra agent is about infrastructure health. They have different polling intervals, different failure modes, and different LLM needs. Combining them would create a bloated agent that's hard to debug when things go wrong.

---

## 10. Resolved Decisions

| Decision | Answer |
|----------|--------|
| Job profiles | `zeal` (SRE/Cloud Lead), `yassir` (IC SWE), `freelance`, `personal` |
| Team member config | Hardcoded in profile YAML |
| Calendar provider | Google Calendar |
| PagerDuty | Zeal only |
| Dashboard auth | Simple PIN/password |
| CLI command | `nerve` |
| Report delivery | Dashboard only |
| LLM hosting | Mix: Ollama (local) + Claude API (heavy tasks) |
| Hosting | Docker on local machine |
| Inter-agent comms | HTTP APIs (Phase 1), Redis pub/sub (Phase 2) |
| Agent comms pattern | Hybrid: conductor routes + agents can call each other directly |
| Build approach | Iterative — conductor + 1-2 agents first |

---

## 11. Remaining Items (Fill Before Building)

1. **Zeal team roster**: Add team member names and emails to `profiles/zeal.yaml` for the followup engine
2. **GitHub org names**: Replace placeholder org names with actual GitHub orgs for both Zeal and Yassir
3. **Jira domain for Yassir**: Confirm the Atlassian domain URL
4. **Yassir Jira project keys**: List the project keys you work with at Yassir
5. **AWS region for Zeal**: Which region are your ECS clusters in?
6. **Grafana URL for Zeal**: The Grafana endpoint for alert monitoring
7. **Slack workspace names**: Confirm workspace identifiers for both jobs
8. **Dashboard PIN**: Choose a PIN for the web dashboard
9. **Timezone**: For scheduling cron jobs (morning briefing, EOD summary)
