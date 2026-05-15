# AutoSRE — Core Application

> See the [top-level README](../README.md) for full documentation, architecture, and deployment instructions.

This directory contains the core AutoSRE application source code.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example ../.env
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000
```

## Directory Layout

| Directory | Purpose |
|-----------|---------|
| `agents/` | 6 AI agents (Planner, Analyst, Researcher, Coder, Communicator, Executor) |
| `gateway/` | FastAPI app, auth, user settings, webhooks |
| `tools/` | External integrations (Slack, GitHub, Jira, Email, Web Search) |
| `memory/` | Redis + PostgreSQL persistence with per-user isolation |
| `dashboard/` | Frontend UI (login, signup, dashboard, settings) |
| `observability/` | Langfuse tracing |
| `taskqueue/` | Celery background task pipeline |
