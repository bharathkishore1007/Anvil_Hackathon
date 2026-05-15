"""
AutoSRE — FastAPI Gateway
Main API application: webhook endpoints, incident management, and dashboard serving.
"""

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Ensure autosre package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from gateway.normalizer import (
    IncidentEvent, normalize_pagerduty, normalize_github,
    normalize_slack, normalize_manual,
)
from gateway.validators import (
    verify_pagerduty_signature, verify_github_signature, verify_slack_signature,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("autosre.gateway")

# ─── FastAPI App ───
app = FastAPI(
    title="AutoSRE — Autonomous Incident Resolution",
    description="Multi-agent AI system for autonomous production incident detection, diagnosis, and resolution.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount dashboard static files
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if os.path.isdir(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="dashboard")


# ─── Pydantic Models ───
class SimulateRequest(BaseModel):
    title: str = "API error rate spiked to 23% on /checkout endpoint"
    description: str = "PagerDuty alert fired — checkout API returning 500 errors at elevated rate since recent deployment."
    severity: str = "high"
    source: str = "pagerduty"
    incident_id: Optional[str] = None


class IncidentResponse(BaseModel):
    incident_id: str
    status: str
    message: str


# ─── In-Memory Store (fallback when Redis/Postgres unavailable) ───
_incidents_store: Dict[str, Any] = {}
_runs_store: list = []


def _process_incident_sync(incident_data: Dict[str, Any]):
    """Process an incident synchronously (used when Celery is unavailable)."""
    from agents.planner import PlannerAgent
    from agents.analyst import AnalystAgent
    from agents.researcher import ResearcherAgent
    from agents.coder import CoderAgent
    from agents.communicator import CommunicatorAgent
    from agents.executor import ExecutorAgent

    incident_id = incident_data["incident_id"]
    logger.info(f"[Sync] Processing incident {incident_id}")

    try:
        # Update state
        _incidents_store[incident_id] = {
            **incident_data,
            "status": "processing",
            "phase": "planning",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "agent_results": {},
        }

        # Store in postgres
        try:
            from memory.postgres_client import get_postgres
            from memory.redis_client import get_redis
            pg = get_postgres()
            pg.create_incident(incident_data)
            redis = get_redis()
            redis.add_active_incident(incident_id)
            redis.set_incident_state(incident_id, {**incident_data, "status": "processing"})
        except Exception as e:
            logger.warning(f"DB storage failed (continuing): {e}")

        # Phase 1: Planning
        logger.info(f"[Sync] Phase 1: Planning for {incident_id}")
        planner = PlannerAgent()
        plan = planner.create_plan(incident_data)

        _incidents_store[incident_id]["execution_plan"] = plan
        _incidents_store[incident_id]["phase"] = "executing"

        try:
            from memory.postgres_client import get_postgres
            pg = get_postgres()
            pg.update_incident(incident_id, {"execution_plan": plan, "status": "investigating"})
        except Exception:
            pass

        # Phase 2: Execute agents
        logger.info(f"[Sync] Phase 2: Executing {len(plan.get('tasks', []))} tasks")
        results = {}

        # Run independent agents first
        for task in plan.get("tasks", []):
            if not task.get("depends_on"):
                agent_type = task.get("agent")
                agent_input = {
                    "input": task.get("input", ""),
                    "title": incident_data.get("title", ""),
                    "severity": incident_data.get("severity", "medium"),
                    "description": incident_data.get("description", ""),
                    "incident_id": incident_id,
                    "similar_incidents": plan.get("similar_incidents", []),
                }
                try:
                    agent_map = {
                        "analyst": AnalystAgent, "researcher": ResearcherAgent,
                        "coder": CoderAgent,
                    }
                    if agent_type in agent_map:
                        agent = agent_map[agent_type]()
                        results[agent_type] = agent.run(agent_input, incident_id)
                        _incidents_store[incident_id]["agent_results"][agent_type] = results[agent_type]
                        logger.info(f"[Sync] {agent_type} completed")
                except Exception as e:
                    logger.error(f"[Sync] {agent_type} failed: {e}")
                    results[agent_type] = {"error": str(e)}

        # Run dependent agents
        for task in plan.get("tasks", []):
            if task.get("depends_on"):
                agent_type = task.get("agent")
                agent_input = {
                    "input": task.get("input", ""),
                    "title": incident_data.get("title", ""),
                    "severity": incident_data.get("severity", "medium"),
                    "description": incident_data.get("description", ""),
                    "incident_id": incident_id,
                    "diagnosis": results.get("analyst", {}),
                    "similar_incidents": plan.get("similar_incidents", []),
                }
                try:
                    agent_map = {
                        "communicator": CommunicatorAgent, "executor": ExecutorAgent,
                    }
                    if agent_type in agent_map:
                        agent = agent_map[agent_type]()
                        results[agent_type] = agent.run(agent_input, incident_id)
                        _incidents_store[incident_id]["agent_results"][agent_type] = results[agent_type]
                        logger.info(f"[Sync] {agent_type} completed")
                except Exception as e:
                    logger.error(f"[Sync] {agent_type} failed: {e}")
                    results[agent_type] = {"error": str(e)}

        # Phase 3: Aggregate
        logger.info(f"[Sync] Phase 3: Aggregating results")
        final = planner.aggregate_results(incident_id, plan, results)

        _incidents_store[incident_id].update({
            "status": "diagnosed_and_escalated",
            "phase": "completed",
            "root_cause": final.get("root_cause", ""),
            "resolution": final.get("summary", ""),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "final_result": final,
        })

        try:
            from memory.postgres_client import get_postgres
            pg = get_postgres()
            pg.update_incident(incident_id, {
                "status": "diagnosed_and_escalated",
                "root_cause": final.get("root_cause", ""),
                "resolution": final.get("summary", ""),
            })
        except Exception:
            pass

        logger.info(f"[Sync] Incident {incident_id} fully resolved")

    except Exception as e:
        logger.error(f"[Sync] Fatal error processing {incident_id}: {e}")
        _incidents_store[incident_id] = {
            **_incidents_store.get(incident_id, incident_data),
            "status": "failed",
            "error": str(e),
        }


# ─── Health Check (cached to avoid repeated timeout delays) ───
_health_cache = {"data": None, "ts": 0}

@app.get("/health")
async def health_check():
    """System health check with 15-second cache."""
    now = time.time()
    if _health_cache["data"] and (now - _health_cache["ts"]) < 15:
        return _health_cache["data"]

    checks = {"api": True}

    # Check Ollama
    try:
        import httpx
        r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        checks["ollama"] = r.status_code == 200
    except Exception:
        checks["ollama"] = False

    # Check Redis
    try:
        from memory.redis_client import get_redis
        checks["redis"] = get_redis().ping()
    except Exception:
        checks["redis"] = False

    # Check PostgreSQL
    try:
        from memory.postgres_client import get_postgres
        checks["postgres"] = get_postgres().ping()
    except Exception:
        checks["postgres"] = False

    result = {
        "status": "healthy" if all(checks.values()) else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }
    _health_cache["data"] = result
    _health_cache["ts"] = now
    return result


# ─── Dashboard ───
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard UI."""
    index_path = os.path.join(dashboard_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>AutoSRE Dashboard</h1><p>Dashboard files not found.</p>")


# ─── Webhook Endpoints ───
@app.post("/webhooks/pagerduty")
async def pagerduty_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive and process PagerDuty alerts."""
    body = await request.body()
    sig = request.headers.get("X-PagerDuty-Signature")
    if not verify_pagerduty_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_pagerduty(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    background_tasks.add_task(_process_incident_sync, incident.model_dump())
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


@app.post("/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive and process GitHub events."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_github(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    background_tasks.add_task(_process_incident_sync, incident.model_dump())
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


@app.post("/webhooks/slack")
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive and process Slack commands."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    sig = request.headers.get("X-Slack-Signature")
    if not verify_slack_signature(body, timestamp, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_slack(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    background_tasks.add_task(_process_incident_sync, incident.model_dump())
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


# ─── Simulation Endpoint ───
@app.post("/incidents/simulate")
async def simulate_incident(req: SimulateRequest, background_tasks: BackgroundTasks):
    """Trigger a simulated incident for demo purposes."""
    incident = normalize_manual(req.model_dump())
    incident_data = incident.model_dump()
    _incidents_store[incident_data["incident_id"]] = incident_data
    logger.info(f"[Simulate] Firing incident: {incident_data['incident_id']}")
    background_tasks.add_task(_process_incident_sync, incident_data)
    return {
        "incident_id": incident_data["incident_id"],
        "status": "accepted",
        "message": "Incident simulation started. Check /incidents/{id} for progress.",
    }


# ─── Incident Management ───
@app.get("/incidents")
async def list_incidents():
    """List all incidents."""
    # Try postgres first
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        db_incidents = pg.list_incidents(limit=50)
        if db_incidents:
            return {"incidents": _serialize(db_incidents), "source": "database"}
    except Exception:
        pass

    # Fallback to in-memory
    incidents = sorted(
        _incidents_store.values(),
        key=lambda x: x.get("timestamp", ""),
        reverse=True,
    )
    return {"incidents": _serialize(incidents), "source": "memory"}


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get detailed incident information including agent traces."""
    # Try postgres
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        incident = pg.get_incident(incident_id)
        if incident:
            runs = pg.get_agent_runs(incident_id)
            return {
                "incident": _serialize_single(incident),
                "agent_runs": _serialize(runs),
                "source": "database",
            }
    except Exception:
        pass

    # Fallback to in-memory
    if incident_id in _incidents_store:
        return {"incident": _serialize_single(_incidents_store[incident_id]), "source": "memory"}

    raise HTTPException(status_code=404, detail="Incident not found")


@app.get("/runs")
async def list_runs():
    """List all agent runs (observability endpoint)."""
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        runs = pg.list_all_runs(limit=100)
        return {"runs": _serialize(runs), "total": len(runs)}
    except Exception:
        return {"runs": [], "total": 0, "note": "Database unavailable"}


@app.get("/system/status")
async def system_status():
    """Get full system status for dashboard."""
    try:
        from memory.redis_client import get_redis
        redis = get_redis()
        active = redis.get_active_incidents()
    except Exception:
        active = list(_incidents_store.keys())

    total = len(_incidents_store)
    resolved = sum(1 for i in _incidents_store.values() if i.get("status") in ("resolved", "diagnosed_and_escalated"))

    return {
        "active_incidents": active,
        "total_incidents": total,
        "resolved_incidents": resolved,
        "in_memory_incidents": list(_incidents_store.keys()),
        "agents": ["planner", "analyst", "researcher", "coder", "communicator", "executor"],
        "ollama_model": settings.OLLAMA_MODEL,
        "integrations": {
            "slack": settings.has_slack(),
            "github": settings.has_github(),
            "jira": settings.has_jira(),
            "langfuse": settings.has_langfuse(),
            "email": settings.has_email(),
            "ollama": True,
        },
        "langfuse_url": settings.LANGFUSE_BASE_URL if settings.has_langfuse() else None,
    }


def _serialize(items):
    """Serialize a list, handling datetime objects."""
    result = []
    for item in items:
        result.append(_serialize_single(item))
    return result


def _serialize_single(item):
    """Serialize a single item."""
    if isinstance(item, dict):
        return {k: _serialize_value(v) for k, v in item.items()}
    return item


def _serialize_value(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return _serialize_single(v)
    if isinstance(v, list):
        return [_serialize_value(i) for i in v]
    return v


# ─── Main ───
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting AutoSRE Gateway...")
    uvicorn.run(
        "gateway.main:app",
        host=settings.GATEWAY_HOST,
        port=settings.GATEWAY_PORT,
        reload=True,
    )
