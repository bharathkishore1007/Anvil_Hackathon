# AutoSRE — Autonomous Multi-Agent Incident Resolution System

> An end-to-end autonomous AI system where multiple specialized agents collaborate to detect, investigate, diagnose, and resolve production incidents — without continuous human intervention.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                 EVENT INGESTION LAYER                │
│  PagerDuty Alert  │  GitHub Webhook  │  Slack CMD   │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI GATEWAY (:8000)                 │
│  Auth · Validation · Event Normalization             │
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
│           PLANNER AGENT (Ollama LLM)                │
│  Decomposes task → JSON execution plan              │
│  Assigns subtasks → tracks progress                 │
└───┬──────────┬──────────┬──────────┬───────────────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
│Analyst │ │Research│ │ Coder  │ │Communic. │ │Executor  │
│ Agent  │ │ Agent  │ │ Agent  │ │  Agent   │ │  Agent   │
└────────┘ └────────┘ └────────┘ └──────────┘ └──────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│          MEMORY & STATE LAYER                       │
│  Redis (short-term) · PostgreSQL + pgvector         │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker Desktop (for Redis + PostgreSQL)
- Ollama with `qwen2.5-coder:3b` and/or `deepseek-coder:1.3b`

### 1. Start Infrastructure
```bash
cd autosre
docker compose up -d
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example ../.env
# Edit ../.env with your API keys
```

### 4. Start the Gateway
```bash
cd autosre
python -m gateway.main
```

### 5. Open Dashboard
Navigate to **http://localhost:8000** in your browser.

### 6. Simulate an Incident
Click the **"Simulate Incident"** button on the dashboard, or run:
```bash
python demo/simulate_incident.py
```

## 🤖 Agent Roles

| Agent | Role | Tools |
|-------|------|-------|
| **Planner** | Orchestrates the pipeline, decomposes incidents into task DAGs | Memory query, task dispatch |
| **Analyst** | Reads logs, metrics, stack traces; produces root cause diagnosis | `parse_logs`, `query_metrics`, `correlate_events` |
| **Researcher** | Searches web and runbooks for similar incidents and fixes | `web_search`, `fetch_url`, `query_runbook_db` |
| **Coder** | Writes diagnostic scripts, health checks, analyzes source code | `execute_python`, `read_file`, `write_file` |
| **Communicator** | Posts structured Slack messages with incident context | `slack_post_message`, `slack_create_thread` |
| **Executor** | Creates GitHub issues, Jira tickets, triggers rollbacks | `github_create_issue`, `jira_create_ticket`, `trigger_rollback` |

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/health` | System health check |
| `POST` | `/incidents/simulate` | Trigger simulated incident |
| `GET` | `/incidents` | List all incidents |
| `GET` | `/incidents/{id}` | Get incident details + agent trace |
| `GET` | `/runs` | List all agent runs (observability) |
| `GET` | `/system/status` | Full system status |
| `POST` | `/webhooks/pagerduty` | PagerDuty webhook |
| `POST` | `/webhooks/github` | GitHub webhook |
| `POST` | `/webhooks/slack` | Slack command webhook |

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11 |
| API Framework | FastAPI |
| Task Queue | Celery + Redis |
| AI Backbone | Ollama (qwen2.5-coder:3b / deepseek-coder:1.3b) |
| Short-term Memory | Redis |
| Long-term Memory | PostgreSQL + pgvector |
| Observability | Langfuse |
| Integrations | Slack API, GitHub API, Jira API |
| Containerization | Docker Compose |

## 📂 Project Structure

```
autosre/
├── gateway/
│   ├── main.py              # FastAPI app, webhook endpoints
│   ├── validators.py        # HMAC signature checks
│   └── normalizer.py        # Event → standard envelope
├── queue/
│   ├── celery_app.py        # Celery + Redis config
│   └── tasks.py             # Task definitions + pipeline runner
├── agents/
│   ├── base.py              # Base agent (Ollama integration)
│   ├── planner.py           # Planner agent
│   ├── researcher.py        # Researcher agent
│   ├── analyst.py           # Analyst agent
│   ├── coder.py             # Coder agent
│   ├── communicator.py      # Communicator agent
│   └── executor.py          # Executor agent
├── memory/
│   ├── redis_client.py      # Short-term state
│   ├── postgres_client.py   # Incident history
│   └── vector_store.py      # pgvector similarity search
├── tools/
│   ├── web_search.py        # Web search + runbook DB
│   ├── github_tools.py      # GitHub API integration
│   ├── slack_tools.py       # Slack API integration
│   ├── jira_tools.py        # Jira API integration
│   ├── log_tools.py         # Log parsing + metrics
│   └── code_executor.py     # Sandboxed code execution
├── observability/
│   └── langfuse_client.py   # Langfuse tracing
├── dashboard/
│   ├── index.html           # Dashboard UI
│   ├── styles.css           # Premium dark theme
│   └── app.js               # Real-time dashboard logic
├── demo/
│   └── simulate_incident.py # Demo simulation script
├── docker-compose.yml       # Redis + PostgreSQL
├── init_db.sql              # Database schema + seed data
├── config.py                # Centralized configuration
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

---

*Built for the Autonomous Multi-Agent AI Systems hackathon. Stack: Python · FastAPI · Celery · Redis · PostgreSQL · Ollama · Slack API · GitHub API · Langfuse.*
