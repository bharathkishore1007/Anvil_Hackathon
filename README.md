# 🛡️ AutoSRE — Autonomous Multi-Agent Incident Resolution Platform

> **An AI-powered SaaS platform where 6 specialized agents collaborate to detect, diagnose, and resolve production incidents in ~30 seconds — powered by Gemini 2.5 Flash.**

### 🌐 Live Demo: [autosre-239243701215.asia-south1.run.app](https://autosre-239243701215.asia-south1.run.app)

---

## 🎯 What is AutoSRE?

AutoSRE is a **multi-tenant SaaS** platform that acts as your 24/7 autonomous on-call engineer. When a production incident fires (via PagerDuty, GitHub, or Slack), AutoSRE:

1. **Ingests** the alert via webhooks or manual simulation
2. **Plans** an investigation strategy using the Planner agent
3. **Analyzes** logs, metrics, and deployment history in parallel
4. **Researches** similar past incidents, CVEs, and internal runbooks
5. **Diagnoses** the root cause with confidence scoring
6. **Acts** — creates GitHub issues, Jira tickets, triggers rollbacks
7. **Communicates** — posts structured Slack threads and email reports

All of this happens in **~30 seconds**, fully autonomously.

---

## 🏗️ System Architecture

```
 ┌───────────────────────────────────────────────────────────────┐
 │                      ALERT SOURCES                            │
 │         PagerDuty    ·    GitHub    ·    Slack                 │
 └────────────────────────────┬──────────────────────────────────┘
                              │ Webhooks
                              ▼
 ┌───────────────────────────────────────────────────────────────┐
 │               ⚡ FastAPI Gateway (Cloud Run)                  │
 │   JWT Auth · Rate Limiting · Event Normalization · REST API   │
 └────────────────────────────┬──────────────────────────────────┘
                              │
                              ▼
 ┌───────────────────────────────────────────────────────────────┐
 │               🧠 Multi-Agent Orchestration                    │
 │                                                               │
 │    ┌──────────┐                                               │
 │    │ Planner  │──── Decomposes incident → Task DAG            │
 │    └────┬─────┘                                               │
 │         │  parallel execution                                 │
 │    ┌────┴─────────────────────────────────┐                   │
 │    │         5 Specialized Workers         │                   │
 │    │                                       │                   │
 │    │  🔍 Analyst        📚 Researcher     │                   │
 │    │  💻 Coder          📢 Communicator   │                   │
 │    │  ⚡ Executor                          │                   │
 │    └───────────────────────────────────────┘                   │
 └────────────────────────────┬──────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │ Gemini   │    │  Memory  │    │  Tools   │
       │ 2.5 Flash│    │ Postgres │    │ Slack    │
       │   LLM    │    │  (Neon)  │    │ GitHub   │
       │          │    │  Redis   │    │ Jira     │
       └──────────┘    └──────────┘    │ Email    │
                                       └──────────┘
```

---

## 🤖 The 6 AI Agents

| Agent | Role | What It Does |
|-------|------|--------------|
| 🧠 **Planner** | Orchestrator | Decomposes the incident into a task DAG (directed acyclic graph) and assigns subtasks |
| 🔍 **Analyst** | Diagnostics | Parses logs, queries metrics, correlates events to pinpoint root cause with confidence score |
| 📚 **Researcher** | Knowledge | Searches the web, CVE databases, and internal runbooks for similar incidents and fixes |
| 💻 **Coder** | Engineering | Analyzes source code, generates diagnostic scripts, identifies buggy files |
| 📢 **Communicator** | Notifications | Posts structured Slack threads and sends HTML email reports to stakeholders |
| ⚡ **Executor** | Actions | Creates GitHub issues, Jira tickets, triggers deployment rollbacks |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **AI / LLM** | Google Gemini 2.5 Flash (via Google GenAI API) |
| **Backend** | Python 3.11 + FastAPI + Uvicorn |
| **Auth** | JWT + bcrypt password hashing + rate limiting |
| **Database** | PostgreSQL (Neon Cloud) — per-user data isolation |
| **Caching** | Redis (short-term incident state) |
| **Secrets** | AES-256 Fernet encryption at rest |
| **Dashboard** | Vanilla HTML/CSS/JS — premium dark theme |
| **Deployment** | Google Cloud Run (auto-scaling, serverless) |
| **Integrations** | Slack API, GitHub API, Jira API, SMTP Email |
| **Observability** | Langfuse — full LLM tracing + Omium |
| **CI/CD** | GitHub → Cloud Build → Cloud Run |

---

## 🔐 Security & Multi-Tenancy

AutoSRE is built as a **secure, multi-tenant SaaS application** with strict data isolation:

| Feature | Implementation |
|---------|---------------|
| **Authentication** | JWT tokens with bcrypt password hashing (72-byte safe) |
| **Rate Limiting** | 5 attempts/minute per IP on login and signup |
| **Data Isolation** | Per-user `user_id` filtering on all incident queries |
| **Encrypted Secrets** | User API keys stored with AES-256 Fernet encryption |
| **Sanitized Errors** | No internal details leaked in error responses |
| **Protected Endpoints** | `/admin/*`, `/runs`, `/incidents/{id}` require JWT auth |
| **Ownership Checks** | Users can only view their own incidents |

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+**
- **Google Gemini API key** (or Ollama for local inference)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/bharathkishore1007/Anvil_Hackathon.git
cd Anvil_Hackathon/autosre

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example ../.env
# Edit ../.env — add your GEMINI_API_KEY, DATABASE_URL, JWT_SECRET, etc.

# 4. Start the server
python -m uvicorn gateway.main:app --host 0.0.0.0 --port 8000

# 5. Open the dashboard
# Visit http://localhost:8000
```

### Optional: Full Infrastructure (Docker)

```bash
docker-compose up -d        # Starts Redis + PostgreSQL
psql -f init_db.sql          # Initialize database schema
```

> **Note:** AutoSRE works without Docker — it gracefully falls back to in-memory storage.

---

## 📊 Dashboard Features

| Feature | Description |
|---------|-------------|
| **Incident Feed** | Live list of all incidents with severity badges and status |
| **Agent Pipeline** | Visual graph showing all 6 agents with real-time status |
| **Root Cause View** | Click any incident to see diagnosis, timeline, and execution plan |
| **Integrations Panel** | Per-user connection status for Slack, GitHub, Jira, Email, Langfuse, Omium |
| **Profile Menu** | Settings, password change, and logout dropdown |
| **Welcome Popup** | First-time users see a guided onboarding prompt |
| **Simulate Incident** | One-click demo — fires a realistic PagerDuty-style incident |

### Demo Flow

1. **Sign up** at `/signup`
2. Click **⚡ Simulate Incident** on the dashboard
3. Hit **🔥 Fire Incident**
4. Watch 6 agents process in real-time (~30 seconds)
5. Click the incident card to see root cause + agent traces

---

## 🔌 Integrations

| Integration | Purpose | Per-User |
|-------------|---------|----------|
| **Slack** | Incident threads + diagnosis updates | ✅ |
| **GitHub** | Auto-create issues + trigger rollbacks | ✅ |
| **Jira** | Ticket creation for tracking | ✅ |
| **Email (SMTP)** | HTML incident reports to stakeholders | ✅ |
| **Langfuse** | LLM observability + tracing | ✅ |
| **Omium** | Additional observability | ✅ |

All integration credentials are **encrypted at rest** using AES-256 (Fernet) and stored per-user.

---

## 🧪 Example Incident Flow

**Input:** _"API error rate spiked to 23% on /checkout endpoint"_

| Step | Agent | Output | Duration |
|------|-------|--------|----------|
| 1 | 🧠 Planner | Creates 6-task parallel execution plan | ~14s |
| 2 | 🔍 Analyst | Root cause: `NullPointerException in OrderValidator.validate()` at line 142 | ~8s |
| 3 | 📚 Researcher | Finds matching runbook (RB-001) + deployment rollback best practices | ~8s |
| 4 | 💻 Coder | Identifies bug in `order_validator.py` — missing null check on `shipping_address` | ~6s |
| 5 | ⚡ Executor | GitHub issue created, Jira ticket filed, rollback triggered | ~3s |
| 6 | 📢 Communicator | Slack thread posted with full diagnosis | ~2s |

**Result:** Root cause identified with **98% confidence** in ~30 seconds.

---

## 🔑 API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/` | — | Dashboard UI |
| `GET` | `/health` | — | System health check |
| `GET` | `/login` | — | Login page |
| `GET` | `/signup` | — | Signup page |
| `GET` | `/settings` | — | Integration settings page |
| `POST` | `/auth/signup` | — | Register new user |
| `POST` | `/auth/login` | — | Authenticate and get JWT |
| `POST` | `/auth/change-password` | JWT | Change user password |
| `POST` | `/incidents/simulate` | JWT | Fire a simulated incident |
| `GET` | `/incidents` | JWT | List user's incidents |
| `GET` | `/incidents/{id}` | JWT | Get incident details + agent traces |
| `GET` | `/runs` | JWT | List agent runs |
| `GET` | `/settings/integrations` | JWT | Get user's integration config |
| `PUT` | `/settings/integrations` | JWT | Save integration credentials |
| `POST` | `/settings/integrations/test/{id}` | JWT | Test integration connectivity |
| `GET` | `/system/status` | — | Sanitized system info |
| `POST` | `/webhooks/pagerduty` | HMAC | PagerDuty webhook |
| `POST` | `/webhooks/github` | HMAC | GitHub webhook |
| `POST` | `/webhooks/slack` | HMAC | Slack webhook |

---

## 📁 Project Structure

```
autosre/
├── agents/                    # 6 AI Agents
│   ├── base.py                # Base agent with Gemini/Ollama integration
│   ├── planner.py             # Task DAG orchestrator
│   ├── analyst.py             # Log/metrics analysis
│   ├── researcher.py          # Web search + runbooks + CVE lookup
│   ├── coder.py               # Code analysis + diagnostic scripts
│   ├── communicator.py        # Slack + email notifications
│   └── executor.py            # GitHub/Jira/rollback actions
├── gateway/                   # FastAPI Application
│   ├── main.py                # API endpoints + multi-tenant filtering
│   ├── auth.py                # JWT auth + bcrypt + rate limiting
│   ├── user_settings.py       # Per-user encrypted settings
│   ├── normalizer.py          # Webhook payload normalization
│   └── validators.py          # HMAC signature verification
├── tools/                     # External Service Integrations
│   ├── slack_tools.py         # Slack Block Kit messages
│   ├── github_tools.py        # GitHub Issues + Deployments
│   ├── jira_tools.py          # Jira ticket creation
│   ├── email_tools.py         # SMTP email with HTML templates
│   ├── web_search.py          # DuckDuckGo + runbook database
│   ├── log_tools.py           # Log parsing + metrics simulation
│   └── code_executor.py       # Sandboxed Python execution
├── memory/                    # Data Persistence
│   ├── redis_client.py        # Redis with in-memory fallback
│   ├── postgres_client.py     # PostgreSQL with user_id isolation
│   └── vector_store.py        # pgvector similarity search
├── observability/             # Monitoring
│   └── langfuse_client.py     # Langfuse tracing + console fallback
├── dashboard/                 # Frontend (Premium Dark Theme)
│   ├── index.html             # Main dashboard
│   ├── login.html             # Branded login (split layout)
│   ├── signup.html            # Branded signup (pipeline visualization)
│   ├── settings.html          # Integration settings UI
│   ├── styles.css             # Design system
│   ├── app.js                 # Real-time polling + JWT-aware fetch
│   └── logo.png               # Brand logo
├── taskqueue/                 # Background Processing
│   ├── celery_app.py          # Celery configuration
│   └── tasks.py               # Async task pipeline
├── demo/                      # Demo Utilities
│   └── simulate_incident.py
├── config.py                  # Centralized settings from .env
├── .env.example               # Template (no secrets)
├── requirements.txt           # Python dependencies
├── docker-compose.yml         # Redis + PostgreSQL (local dev)
└── init_db.sql                # Database schema + seed data
```

---

## 🌍 Deployment

AutoSRE is deployed on **Google Cloud Run** with the following infrastructure:

| Service | Provider | Purpose |
|---------|----------|---------|
| **Compute** | Google Cloud Run | Auto-scaling serverless containers |
| **Database** | Neon (PostgreSQL) | Managed serverless Postgres |
| **Cache** | Upstash (Redis) | Managed serverless Redis |
| **AI** | Google Gemini 2.5 Flash | LLM inference |
| **Build** | Google Cloud Build | CI/CD pipeline |

### Deploy to Cloud Run

```bash
gcloud run deploy autosre \
  --source ./autosre \
  --region asia-south1 \
  --allow-unauthenticated
```

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `DATABASE_URL` | PostgreSQL connection string (Neon) |
| `JWT_SECRET` | Secret key for JWT token signing |
| `SETTINGS_ENCRYPTION_KEY` | Fernet key for encrypting user API keys |
| `REDIS_URL` | Redis connection string |

---

## 👨‍💻 Team

Built for the **Anvil Hackathon 2026** by:

- **Bharath Kishore** — [@bharathkishore1007](https://github.com/bharathkishore1007)

---

## 📜 License

MIT License — see [LICENSE](LICENSE) for details.
