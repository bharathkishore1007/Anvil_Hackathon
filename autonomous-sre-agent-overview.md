# AutoSRE — Autonomous Multi-Agent Incident Resolution System

> An end-to-end autonomous AI system where multiple specialized agents collaborate to detect, investigate, diagnose, and resolve production incidents — without continuous human intervention.

---

## Problem Statement

Modern engineering teams lose hours responding to production incidents manually: someone gets paged, checks logs, searches for similar issues, writes a postmortem, creates tickets, and notifies stakeholders. This process is slow, error-prone, and happens at 3am. AutoSRE replaces the reactive human loop with a fully autonomous agent pipeline that handles the entire incident lifecycle — from alert to resolution report — independently.

---

## Project Overview

AutoSRE is a **long-running autonomous workflow** built on top of the Anthropic Claude API. It is not a chatbot. It is a production-style operations system where multiple AI agents — each with a distinct role and toolset — collaborate asynchronously to complete real operational work and produce real side effects: Slack messages, GitHub issues, Jira tickets, and deployment rollbacks.

### Core Capabilities

- Ingest live events from GitHub, PagerDuty, Slack, and cron schedules via webhooks
- Decompose incoming incidents into subtasks using a Claude-powered Planner Agent
- Dispatch subtasks asynchronously to specialized worker agents via a task queue
- Execute web searches, analyze logs, write and run code, and call external APIs
- Post structured updates to Slack, create GitHub issues, and trigger rollbacks
- Maintain persistent memory of past incidents for pattern recognition
- Expose full observability — every agent call, decision, and tool use is logged and traceable

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                 EVENT INGESTION LAYER                │
│  GitHub Webhook  │  Slack Command  │  PagerDuty Alert│
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI GATEWAY                        │
│  Auth · Validation · Event normalization            │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│           TASK QUEUE (Celery + Redis)               │
│  Priority lanes · Retries · Dead-letter queue       │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│           PLANNER AGENT (Claude)                    │
│  Decomposes task → JSON execution plan              │
│  Assigns subtasks to workers → tracks progress     │
└───┬──────────┬──────────┬──────────┬───────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌───────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
│Reseach│ │Analyst │ │ Coder  │ │Communic. │ │Executor  │
│Agent  │ │ Agent  │ │ Agent  │ │  Agent   │ │  Agent   │
└───┬───┘ └───┬────┘ └───┬────┘ └───┬──────┘ └───┬──────┘
    │         │          │          │              │
    └─────────┴──────────┴──────────┴──────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│          MEMORY & STATE LAYER                       │
│  Redis (short-term) · Postgres (history)            │
│  pgvector (similar incident retrieval)              │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│           REAL SIDE EFFECTS (outputs)               │
│  Slack message · GitHub issue · Jira ticket         │
│  Incident report · Deployment rollback trigger      │
└─────────────────────────────────────────────────────┘
```

---

## Agent Roles

### Planner Agent
The orchestrator. Receives a normalized incident event and produces a structured JSON execution plan. Assigns each subtask to the appropriate worker, tracks completion, aggregates results, and makes the final resolution decision.

**System prompt focus:** Task decomposition, worker capability matching, failure handling, replanning on partial failure.

### Researcher Agent
Searches the web and internal runbooks for relevant context. Given an error message or alert, it surfaces similar incidents, known fixes, and relevant documentation.

**Tools:** `web_search`, `fetch_url`, `query_runbook_db`

### Analyst Agent
Reads raw logs, metrics, and stack traces. Produces a structured diagnosis: what failed, likely root cause, confidence score, and recommended action.

**Tools:** `parse_logs`, `query_metrics_api`, `correlate_events`

### Coder Agent
Writes and executes code in a sandboxed environment. Used for log parsing scripts, automated health checks, or generating postmortem templates.

**Tools:** `execute_python`, `read_file`, `write_file`

### Communicator Agent
Handles all external messaging. Posts incident updates to Slack with structured formatting, sends email summaries, and notifies on-call rotation members.

**Tools:** `slack_post_message`, `slack_create_thread`, `send_email`

### Executor Agent
Takes real action. Creates GitHub issues, comments on PRs, creates Jira tickets, and triggers deployment rollbacks via webhooks. This is the agent that produces the most visible side effects.

**Tools:** `github_create_issue`, `github_comment_pr`, `jira_create_ticket`, `trigger_rollback_webhook`

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| API framework | FastAPI |
| Task queue | Celery + Redis |
| AI backbone | Anthropic Claude API (`claude-sonnet-4-6`) |
| Short-term memory | Redis |
| Long-term memory | PostgreSQL + pgvector |
| Code execution | E2B sandbox / subprocess |
| Observability | Langfuse |
| External integrations | GitHub API, Slack API, Jira API |
| Containerization | Docker Compose |

---

## Demo Scenario (End-to-End)

The following scenario runs completely autonomously after a single webhook fires.

**Trigger:** A PagerDuty alert fires — "API error rate spiked to 23% on /checkout endpoint."

**Step 1 — Gateway** receives the alert, validates the signature, normalizes the event, and publishes a job to the high-priority queue.

**Step 2 — Planner Agent** picks up the job and produces this plan:
```json
{
  "incident_id": "INC-2847",
  "tasks": [
    { "id": "t1", "agent": "analyst", "input": "last 1hr logs /checkout" },
    { "id": "t2", "agent": "researcher", "input": "checkout API 23% error rate" },
    { "id": "t3", "agent": "executor", "depends_on": ["t1","t2"], "action": "create_github_issue" },
    { "id": "t4", "agent": "communicator", "depends_on": ["t1"], "action": "post_slack_update" }
  ]
}
```

**Step 3 — Analyst Agent** reads logs, finds a null pointer exception introduced in the last deploy 47 minutes ago.

**Step 4 — Researcher Agent** finds a similar incident from 3 months ago with a known fix (revert a specific config flag).

**Step 5 — Executor Agent** creates a GitHub issue titled "INC-2847: Checkout null pointer — deploy revert needed" with full context, labels, and assignees.

**Step 6 — Communicator Agent** posts a structured Slack message to #incidents:
> 🔴 **INC-2847 | Checkout API — 23% error rate**
> Root cause: null pointer in `order_validator.py` (introduced 47min ago)
> Action taken: GitHub issue created, revert recommended
> Similar incident: INC-2301 (resolved in 12min via config revert)

**Step 7 — Planner Agent** aggregates all results, marks the incident as "diagnosed and escalated", and writes a summary to the incident history table.

Total time from alert to Slack message: **under 90 seconds.** Zero human input.

---

## Key Differentiators for Judges

**True autonomy** — after the initial webhook, no human input is required at any step. The system replans if a worker fails.

**Real multi-agent orchestration** — agents do not just run in sequence. The planner issues parallel subtasks, waits on dependencies, and aggregates partial results.

**Deep reasoning** — the Planner Agent produces an explicit JSON reasoning trace for every decision, making its logic inspectable.

**Async execution** — Celery workers run independently and report back. The system handles partial failures gracefully with automatic retries and fallback plans.

**Real side effects** — GitHub issues, Slack messages, and Jira tickets are actually created during a live demo. Not simulated.

**Persistent memory** — past incidents are stored with vector embeddings so agents can retrieve and cite similar past resolutions.

**Full observability** — every agent invocation, tool call, token count, and decision is logged to Langfuse and queryable via a `/runs` API endpoint.

---

## Project Structure

```
autosre/
├── gateway/
│   ├── main.py              # FastAPI app, webhook endpoints
│   ├── validators.py        # HMAC signature checks
│   └── normalizer.py        # Event → standard envelope
├── queue/
│   ├── celery_app.py        # Celery + Redis config
│   └── tasks.py             # Task definitions
├── agents/
│   ├── planner.py           # Planner agent logic
│   ├── researcher.py        # Researcher agent + tools
│   ├── analyst.py           # Analyst agent + tools
│   ├── coder.py             # Coder agent + sandbox
│   ├── communicator.py      # Communicator agent + Slack
│   └── executor.py          # Executor agent + GitHub/Jira
├── memory/
│   ├── redis_client.py      # Short-term state
│   ├── postgres_client.py   # Incident history
│   └── vector_store.py      # pgvector similarity search
├── tools/
│   ├── web_search.py
│   ├── github_tools.py
│   ├── slack_tools.py
│   └── jira_tools.py
├── observability/
│   └── langfuse_client.py
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Build Order (8-Day Plan)

| Day | Milestone |
|---|---|
| 1–2 | Gateway + Celery queue. Events flow reliably into Redis. |
| 3–4 | Planner agent. Correctly decomposes a fake incident into a JSON plan. |
| 5 | Analyst + Communicator agents. First full loop: alert → diagnosis → Slack message. |
| 6 | Executor agent. GitHub issue creation and Jira ticket on incident close. |
| 7 | Memory layer + Langfuse observability. Similar incident retrieval works. |
| 8 | Polish demo scenario. Docker Compose everything. Write README with demo video. |

---

## Success Criteria

The project is complete when the following happens with zero human input after the webhook fires:

- [ ] Incident is detected and normalized by the gateway
- [ ] Planner produces a correct multi-step execution plan
- [ ] At least two worker agents run in parallel
- [ ] A Slack message is posted with structured incident context
- [ ] A GitHub issue is created with full diagnosis
- [ ] A similar past incident is retrieved from memory and cited
- [ ] The full agent trace is visible in Langfuse
- [ ] The system retries gracefully if one worker fails

---

*Built for the Autonomous Multi-Agent AI Systems challenge. Stack: Python · FastAPI · Celery · Redis · PostgreSQL · Claude API · Slack API · GitHub API · Langfuse.*
