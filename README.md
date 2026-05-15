# 🛡️ AutoSRE — Autonomous Incident Resolution System

> An AI-powered multi-agent platform that detects, investigates, diagnoses, and resolves production incidents **without human intervention** — powered entirely by local LLMs.

---

## 🎯 What is AutoSRE?

AutoSRE is an autonomous Site Reliability Engineering (SRE) agent that acts as a 24/7 on-call engineer. When a production incident fires (via PagerDuty, GitHub, or Slack), AutoSRE:

1. **Receives** the alert via webhooks
2. **Plans** an investigation strategy using AI
3. **Analyzes** logs, metrics, and deployment history
4. **Researches** similar past incidents and runbooks
5. **Diagnoses** the root cause with confidence scoring
6. **Takes action** — creates GitHub issues, Jira tickets, triggers rollbacks
7. **Communicates** — posts to Slack and sends email reports

All of this happens in **~35 seconds**, with zero human input.

---

## 🏗️ Architecture

```
 ┌─────────────────────────────────────────────────────────────┐
 │                    ALERT SOURCES                            │
 │        PagerDuty    ·    GitHub    ·    Slack                │
 └──────────────────────────┬──────────────────────────────────┘
                            │ Webhooks
                            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                  ⚡ FastAPI Gateway (:8000)                  │
 │     Normalizer  ·  Validator  ·  Dashboard  ·  REST API     │
 └──────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                  🧠 Agent Orchestration                      │
 │                                                              │
 │    ┌──────────┐                                              │
 │    │ Planner  │──── Creates task DAG from incident           │
 │    └────┬─────┘                                              │
 │         │                                                    │
 │    ┌────┴──────────────────────────────┐                     │
 │    │         Worker Agents             │                     │
 │    │                                   │                     │
 │    │  🔍 Analyst      📚 Researcher   │                     │
 │    │  💻 Coder        📢 Communicator │                     │
 │    │  ⚡ Executor                      │                     │
 │    └───────────────────────────────────┘                     │
 └──────────────────────────┬───────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
     ┌──────────┐    ┌──────────┐    ┌──────────┐
     │  Ollama  │    │  Memory  │    │  Tools   │
     │  (Local) │    │ Redis/PG │    │ Slack    │
     │  LLM     │    │ In-Mem   │    │ GitHub   │
     │          │    │ Fallback │    │ Jira     │
     └──────────┘    └──────────┘    │ Email    │
                                     └──────────┘
```

---

## 🤖 The 6 Agents

| Agent | Role | What It Does |
|-------|------|--------------|
| 🧠 **Planner** | Orchestrator | Breaks the incident into a task DAG (directed acyclic graph) |
| 🔍 **Analyst** | Diagnostics | Parses logs, queries metrics, correlates events to find root cause |
| 📚 **Researcher** | Knowledge | Searches the web + internal runbook database for similar incidents |
| 💻 **Coder** | Engineering | Generates and runs diagnostic scripts |
| 📢 **Communicator** | Notifications | Posts to Slack, sends HTML email reports to stakeholders |
| ⚡ **Executor** | Actions | Creates GitHub issues, Jira tickets, triggers deployment rollbacks |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **AI / LLM** | Ollama (local) — `qwen2.5-coder:3b` / `deepseek-coder:1.3b` |
| **Backend** | Python 3.14 + FastAPI + Uvicorn |
| **Dashboard** | Vanilla HTML/CSS/JS — premium dark theme |
| **Messaging** | Slack Bot (Block Kit messages) |
| **Issue Tracking** | GitHub Issues API + Jira Cloud API |
| **Email** | SMTP (Gmail) — styled HTML incident reports |
| **Observability** | Langfuse — full LLM tracing |
| **Memory** | Redis (short-term) + PostgreSQL (long-term) |
| **Fallback** | In-memory store when Redis/PG unavailable |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Ollama** installed and running (`ollama serve`)
- Pull the models:
  ```bash
  ollama pull qwen2.5-coder:3b
  ollama pull deepseek-coder:1.3b
  ```

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/bharathkishore1007/Anvil_Hackathon.git
cd Anvil_Hackathon/autosre

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example ../.env
# Edit ../.env with your API keys (Slack, GitHub, Jira, etc.)

# 4. Start the server
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000

# 5. Open the dashboard
# Visit http://localhost:8000
```

### Optional: Full Infrastructure

```bash
# Start Redis + PostgreSQL via Docker
docker-compose up -d

# Initialize the database
psql -h localhost -U autosre -d autosre -f init_db.sql
```

> **Note:** AutoSRE works without Docker — it gracefully falls back to in-memory storage.

---

## 📊 Dashboard

The real-time dashboard at `http://localhost:8000` shows:

- **Incident Feed** — live list of all incidents with severity and status
- **Agent Orchestration** — visual graph of all 6 agents with live status
- **Incident Details** — root cause, resolution, execution plan, agent results
- **Integrations Panel** — connection status for all 8 services

### How to Demo

1. Open `http://localhost:8000`
2. Click **⚡ Simulate Incident**
3. Hit **🔥 Fire Incident**
4. Watch the agents process in real-time (~35 seconds)
5. Click the incident card to see root cause + execution plan

---

## 🔌 Integrations

| Integration | Purpose | Status |
|-------------|---------|--------|
| **Slack** | Incident threads + diagnosis updates | ✅ Connected |
| **GitHub** | Auto-create issues + trigger rollbacks | ✅ Connected |
| **Jira** | Ticket creation for tracking | ✅ Connected |
| **Langfuse** | LLM observability + tracing | ✅ Connected |
| **Email** | HTML incident reports via SMTP | ✅ Connected |
| **Ollama** | Local LLM inference | ✅ Connected |
| **Redis** | Short-term incident state | Optional |
| **PostgreSQL** | Long-term history + vector search | Optional |

---

## 📁 Project Structure

```
autosre/
├── agents/                 # AI agents
│   ├── base.py             # Base agent with Ollama integration
│   ├── planner.py          # Task decomposition + DAG
│   ├── analyst.py          # Log/metrics analysis
│   ├── researcher.py       # Web search + runbooks
│   ├── coder.py            # Diagnostic scripts
│   ├── communicator.py     # Slack + email notifications
│   └── executor.py         # GitHub/Jira/rollback actions
├── gateway/                # FastAPI application
│   ├── main.py             # API endpoints + dashboard serving
│   ├── normalizer.py       # Webhook payload normalization
│   └── validators.py       # HMAC signature verification
├── tools/                  # External service integrations
│   ├── slack_tools.py      # Slack Block Kit messages
│   ├── github_tools.py     # GitHub Issues + Deployments
│   ├── jira_tools.py       # Jira ticket creation
│   ├── email_tools.py      # SMTP email with HTML templates
│   ├── web_search.py       # DuckDuckGo + runbook database
│   ├── log_tools.py        # Log parsing + metrics simulation
│   └── code_executor.py    # Sandboxed Python execution
├── memory/                 # Data persistence
│   ├── redis_client.py     # Redis with in-memory fallback
│   ├── postgres_client.py  # PostgreSQL with fast-fail cooldown
│   └── vector_store.py     # pgvector similarity search
├── observability/          # Monitoring
│   └── langfuse_client.py  # Langfuse tracing + console fallback
├── dashboard/              # Frontend
│   ├── index.html          # Dashboard UI
│   ├── styles.css          # Premium dark theme
│   └── app.js              # Real-time polling + interaction
├── taskqueue/              # Background processing
│   ├── celery_app.py       # Celery configuration
│   └── tasks.py            # Async task pipeline
├── demo/                   # Demo utilities
│   └── simulate_incident.py
├── config.py               # Centralized settings from .env
├── .env.example            # Template (no secrets)
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # Redis + PostgreSQL
└── init_db.sql             # Database schema
```

---

## 🔑 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/health` | System health check |
| `GET` | `/system/status` | Full integration status |
| `POST` | `/incidents/simulate` | Fire a simulated incident |
| `GET` | `/incidents` | List all incidents |
| `GET` | `/incidents/{id}` | Get incident details + agent runs |
| `POST` | `/webhooks/pagerduty` | PagerDuty webhook receiver |
| `POST` | `/webhooks/github` | GitHub webhook receiver |
| `POST` | `/webhooks/slack` | Slack webhook receiver |

---

## 🧪 Example Incident Flow

**Input:** _"API error rate spiked to 23% on /checkout endpoint"_

| Step | Agent | Output |
|------|-------|--------|
| 1 | 🧠 Planner | Creates 6-task execution plan |
| 2 | 🔍 Analyst | Root cause: `NullPointerException in OrderValidator.validate()` |
| 3 | 📚 Researcher | Finds matching runbook + similar past incident |
| 4 | ⚡ Executor | GitHub issue created, Jira ticket filed, rollback triggered |
| 5 | 📢 Communicator | Slack thread posted, email report sent |

**Result:** Diagnosed with 85% confidence in ~35 seconds.

---

## 🔒 Security

- `.env` is **gitignored** — API keys never committed
- Webhook signature verification (HMAC) for PagerDuty, GitHub, Slack
- Rollbacks are **simulated by default** — requires manual confirmation
- Code execution runs in a sandboxed environment
- All LLM inference runs **locally** — no data leaves your infrastructure

---

## 👨‍💻 Team

Built for the **Anvil Hackathon 2026** by:

- **Bharath Kishore** — [@bharathkishore1007](https://github.com/bharathkishore1007)

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.
