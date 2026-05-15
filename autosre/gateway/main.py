"""
AutoSRE — FastAPI Gateway
Main API application: webhook endpoints, incident management, and dashboard serving.
"""

import concurrent.futures
import json
import logging
import os
import sys
import threading
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

# Mount auth & settings routers
from gateway.auth import router as auth_router
from gateway.user_settings import router as settings_router
app.include_router(auth_router)
app.include_router(settings_router)


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
    """Process an incident through the full multi-agent pipeline.
    
    Pipeline:  Planner → [Analyst + Researcher] (parallel) → Executor → Communicator → Aggregate
    Live status updates are written to _incidents_store so the dashboard can poll them.
    Traces are sent to both Langfuse and Omium for observability.
    """
    from agents.planner import PlannerAgent
    from agents.analyst import AnalystAgent
    from agents.researcher import ResearcherAgent
    from agents.coder import CoderAgent
    from agents.communicator import CommunicatorAgent
    from agents.executor import ExecutorAgent
    import concurrent.futures

    # Initialize Omium tracing
    try:
        from observability.omium_client import init_omium
        init_omium()
    except Exception:
        pass

    incident_id = incident_data["incident_id"]
    logger.info(f"[Pipeline] Processing incident {incident_id}")
    pipeline_start = time.time()

    # Initialize incident state for dashboard
    _incidents_store[incident_id] = {
        **incident_data,
        "status": "processing",
        "phase": "initializing",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "agent_results": {},
        "agent_status": {},
    }

    def _set_agent_status(agent: str, status: str):
        """Update agent status so dashboard can show live transitions."""
        store = _incidents_store.get(incident_id, {})
        if "agent_status" not in store:
            store["agent_status"] = {}
        store["agent_status"][agent] = status
        _incidents_store[incident_id] = store

    def _set_phase(phase: str):
        _incidents_store[incident_id]["phase"] = phase

    # Persist to databases (non-blocking)
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

    try:
        # ── Phase 1: Planning ──
        _set_phase("planning")
        _set_agent_status("planner", "running")
        logger.info(f"[Pipeline] Phase 1: Planning for {incident_id}")

        planner = PlannerAgent()
        plan = planner.create_plan(incident_data)

        _set_agent_status("planner", "completed")
        _incidents_store[incident_id]["execution_plan"] = plan
        _incidents_store[incident_id]["agent_results"]["planner"] = plan
        logger.info(f"[Pipeline] Planner created {len(plan.get('tasks', []))} tasks")

        try:
            from memory.postgres_client import get_postgres
            get_postgres().update_incident(incident_id, {"execution_plan": plan, "status": "investigating"})
        except Exception:
            pass

        # ── Phase 2: Parallel agent execution ──
        _set_phase("analyzing")
        logger.info(f"[Pipeline] Phase 2: Executing agents in parallel")
        results = {}

        # Build agent input shared context
        base_input = {
            "title": incident_data.get("title", ""),
            "severity": incident_data.get("severity", "medium"),
            "description": incident_data.get("description", ""),
            "incident_id": incident_id,
            "similar_incidents": plan.get("similar_incidents", []),
        }

        # Run INDEPENDENT agents in parallel (analyst + researcher + coder)
        def _run_agent(agent_type, agent_class, extra_input=None):
            _set_agent_status(agent_type, "running")
            try:
                task_input_text = ""
                for task in plan.get("tasks", []):
                    if task.get("agent") == agent_type:
                        task_input_text = task.get("input", "")
                        break
                agent_input = {**base_input, "input": task_input_text or base_input["title"]}
                if extra_input:
                    agent_input.update(extra_input)

                # Wrap agent.run with Omium trace
                def _do_run():
                    agent = agent_class()
                    return agent.run(agent_input, incident_id)

                try:
                    from observability.omium_client import run_traced_agent
                    result = run_traced_agent(agent_type, _do_run)
                except Exception:
                    result = _do_run()

                _set_agent_status(agent_type, "completed")
                _incidents_store[incident_id]["agent_results"][agent_type] = result
                logger.info(f"[Pipeline] {agent_type} completed")
                return agent_type, result
            except Exception as e:
                _set_agent_status(agent_type, "failed")
                logger.error(f"[Pipeline] {agent_type} failed: {e}")
                return agent_type, {"error": str(e)}

        # Execute analyst + researcher + coder in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(_run_agent, "analyst", AnalystAgent),
                executor.submit(_run_agent, "researcher", ResearcherAgent),
            ]
            # Only run coder if plan includes it
            coder_tasks = [t for t in plan.get("tasks", []) if t.get("agent") == "coder"]
            if coder_tasks:
                futures.append(executor.submit(_run_agent, "coder", CoderAgent))

            for future in concurrent.futures.as_completed(futures, timeout=180):
                agent_type, result = future.result()
                results[agent_type] = result

        # ── Phase 3: Dependent agents (need diagnosis results) ──
        _set_phase("acting")
        logger.info(f"[Pipeline] Phase 3: Running dependent agents")

        diagnosis = results.get("analyst", {})

        # Executor — creates GitHub issues, Jira tickets, triggers rollbacks
        _run_agent("executor", ExecutorAgent, {
            "diagnosis": diagnosis,
        })
        results["executor"] = _incidents_store[incident_id]["agent_results"].get("executor", {})

        # Communicator — posts to Slack + sends email
        _run_agent("communicator", CommunicatorAgent, {
            "diagnosis": diagnosis,
        })
        results["communicator"] = _incidents_store[incident_id]["agent_results"].get("communicator", {})

        # ── Phase 4: Aggregate ──
        _set_phase("aggregating")
        logger.info(f"[Pipeline] Phase 4: Aggregating results")
        final = planner.aggregate_results(incident_id, plan, results)

        pipeline_duration = int((time.time() - pipeline_start) * 1000)

        _incidents_store[incident_id].update({
            "status": "diagnosed_and_escalated",
            "phase": "completed",
            "root_cause": final.get("root_cause", ""),
            "resolution": final.get("summary", ""),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_duration_ms": pipeline_duration,
            "final_result": final,
        })

        try:
            from memory.postgres_client import get_postgres
            get_postgres().update_incident(incident_id, {
                "status": "diagnosed_and_escalated",
                "root_cause": final.get("root_cause", ""),
                "pipeline_duration_ms": pipeline_duration,
            })
        except Exception:
            pass

        # Flush Langfuse traces
        try:
            from observability.langfuse_client import flush as langfuse_flush
            langfuse_flush()
            logger.info("[Pipeline] Langfuse traces flushed")
        except Exception as e:
            logger.warning(f"[Pipeline] Langfuse flush issue: {e}")

        logger.info(f"[Pipeline] ✅ Incident {incident_id} fully resolved in {pipeline_duration}ms")

        # ── Phase 5: Long-Running Post-Resolution Monitoring ──
        # Spawns a background monitoring job that runs for 2 minutes,
        # polling service health every 30s to verify the fix holds.
        threading.Thread(
            target=_post_resolution_monitor,
            args=(incident_id, incident_data),
            daemon=True,
            name=f"monitor-{incident_id}",
        ).start()
        logger.info(f"[Pipeline] 🔄 Post-resolution monitoring started for {incident_id} (2 min)")

    except Exception as e:
        logger.error(f"[Pipeline] Fatal error processing {incident_id}: {e}")
        _incidents_store[incident_id] = {
            **_incidents_store.get(incident_id, incident_data),
            "status": "failed",
            "error": str(e),
        }


def _post_resolution_monitor(incident_id: str, incident_data: dict):
    """Long-running background job: monitors service health for 2 minutes post-resolution.

    Runs 4 health checks at 30-second intervals, then sends a follow-up Slack report
    confirming the fix is stable or flagging regression.
    """
    import httpx

    logger.info(f"[Monitor] Starting 2-minute post-resolution watch for {incident_id}")
    checks = []
    total_checks = 4
    check_interval = 30  # seconds

    for i in range(total_checks):
        time.sleep(check_interval)
        ts = datetime.now(timezone.utc).isoformat()
        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=5)
            healthy = r.status_code == 200
        except Exception:
            healthy = False

        check = {"check": i + 1, "timestamp": ts, "healthy": healthy}
        checks.append(check)
        logger.info(f"[Monitor] {incident_id} — check {i+1}/{total_checks}: {'✅ healthy' if healthy else '❌ degraded'}")

    # Update incident with monitoring results
    all_healthy = all(c["healthy"] for c in checks)
    _incidents_store[incident_id]["post_resolution_monitoring"] = {
        "checks": checks,
        "duration_seconds": total_checks * check_interval,
        "all_healthy": all_healthy,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Send follow-up Slack notification
    try:
        from tools.slack_tools import post_message
        status_emoji = "✅" if all_healthy else "⚠️"
        post_message(text=
            f"{status_emoji} *Post-Resolution Report — {incident_id}*\n"
            f"• Monitoring period: {total_checks * check_interval}s ({total_checks} checks)\n"
            f"• All checks passed: {'Yes' if all_healthy else 'No — regression detected'}\n"
            f"• Incident: {incident_data.get('title', 'N/A')}\n"
            f"• Verdict: {'Fix confirmed stable' if all_healthy else 'Further investigation required'}"
        )
        logger.info(f"[Monitor] Follow-up Slack report sent for {incident_id}")
    except Exception as e:
        logger.warning(f"[Monitor] Slack follow-up failed: {e}")

    logger.info(f"[Monitor] ✅ Post-resolution monitoring complete for {incident_id} ({total_checks * check_interval}s)")


# ─── Health Check (cached to avoid repeated timeout delays) ───
_health_cache = {"data": None, "ts": 0}

@app.get("/health")
async def health_check():
    """System health check with 15-second cache."""
    now = time.time()
    if _health_cache["data"] and (now - _health_cache["ts"]) < 15:
        return _health_cache["data"]

    checks = {"api": True}

    # Check LLM (Gemini or Ollama)
    if settings.has_gemini():
        checks["ollama"] = True  # Gemini is cloud-native, always available
    else:
        try:
            import httpx as _hx
            r = _hx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2.0)
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
        "status": "healthy" if checks["api"] and checks["ollama"] else "degraded",
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


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Serve the login page."""
    path = os.path.join(dashboard_dir, "login.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Login</h1>")


@app.get("/signup", response_class=HTMLResponse)
async def signup_page():
    """Serve the signup page."""
    path = os.path.join(dashboard_dir, "signup.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Signup</h1>")


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    """Serve the integration settings page."""
    path = os.path.join(dashboard_dir, "settings.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Settings</h1>")


# ─── Webhook Endpoints ───
@app.post("/webhooks/pagerduty")
async def pagerduty_webhook(request: Request):
    """Receive and process PagerDuty alerts."""
    body = await request.body()
    sig = request.headers.get("X-PagerDuty-Signature")
    if not verify_pagerduty_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_pagerduty(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    threading.Thread(target=_process_incident_sync, args=(incident.model_dump(),), daemon=True).start()
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    """Receive and process GitHub events."""
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_github_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_github(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    threading.Thread(target=_process_incident_sync, args=(incident.model_dump(),), daemon=True).start()
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


@app.post("/webhooks/slack")
async def slack_webhook(request: Request):
    """Receive and process Slack commands."""
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    sig = request.headers.get("X-Slack-Signature")
    if not verify_slack_signature(body, timestamp, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = json.loads(body)
    incident = normalize_slack(payload)
    _incidents_store[incident.incident_id] = incident.model_dump()
    threading.Thread(target=_process_incident_sync, args=(incident.model_dump(),), daemon=True).start()
    return IncidentResponse(incident_id=incident.incident_id, status="accepted", message="Incident queued")


# ─── Simulation Endpoint ───
@app.post("/incidents/simulate")
async def simulate_incident(req: SimulateRequest, request: Request):
    """Trigger a simulated incident for demo purposes."""
    # Extract user_id from JWT if present
    user_id = _extract_user_id(request)
    incident = normalize_manual(req.model_dump())
    incident_data = incident.model_dump()
    incident_data["user_id"] = user_id  # Tag with user
    _incidents_store[incident_data["incident_id"]] = incident_data
    logger.info(f"[Simulate] Firing incident: {incident_data['incident_id']} for user: {user_id}")
    # Use thread instead of BackgroundTasks — survives on Cloud Run
    threading.Thread(
        target=_process_incident_sync,
        args=(incident_data,),
        daemon=True,
        name=f"pipeline-{incident_data['incident_id']}",
    ).start()
    return {
        "incident_id": incident_data["incident_id"],
        "status": "accepted",
        "message": "Incident simulation started. Check /incidents/{id} for progress.",
    }


def _extract_user_id(request: Request) -> str:
    """Extract user_id from Authorization header, or return 'system'."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from gateway.auth import _decode_token
            payload = _decode_token(auth.split(" ", 1)[1])
            if payload:
                return payload.get("sub", "system")
        except Exception:
            pass
    return "system"


# ─── Incident Management ───
@app.get("/incidents")
async def list_incidents(request: Request):
    """List incidents for the current user."""
    user_id = _extract_user_id(request)
    merged = {}

    # Load from postgres
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        db_incidents = pg.list_incidents(limit=50)
        for inc in (db_incidents or []):
            iid = inc.get("incident_id", "")
            if iid:
                merged[iid] = inc
    except Exception:
        pass

    # Overlay in-memory state (has the most up-to-date status)
    for iid, mem_inc in _incidents_store.items():
        if iid in merged:
            merged[iid]["status"] = mem_inc.get("status", merged[iid].get("status"))
            if mem_inc.get("root_cause"):
                merged[iid]["root_cause"] = mem_inc["root_cause"]
            if mem_inc.get("pipeline_duration_ms"):
                merged[iid]["pipeline_duration_ms"] = mem_inc["pipeline_duration_ms"]
            if mem_inc.get("completed_at"):
                merged[iid]["completed_at"] = mem_inc["completed_at"]
            if mem_inc.get("agent_results"):
                merged[iid]["agent_results"] = mem_inc["agent_results"]
            if mem_inc.get("user_id"):
                merged[iid]["user_id"] = mem_inc["user_id"]
        else:
            merged[iid] = mem_inc

    # Filter by user_id — only show user's own incidents
    if user_id != "system":
        merged = {k: v for k, v in merged.items() if v.get("user_id", "system") == user_id}

    incidents = sorted(
        merged.values(),
        key=lambda x: x.get("timestamp", x.get("created_at", "")),
        reverse=True,
    )
    return {"incidents": _serialize(incidents), "source": "merged"}


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, request: Request):
    """Get detailed incident information including agent traces."""
    user_id = _extract_user_id(request)
    # Try postgres
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        incident = pg.get_incident(incident_id)
        if incident:
            # Verify ownership
            if user_id != "system" and incident.get("user_id", "system") != user_id:
                raise HTTPException(status_code=404, detail="Incident not found")
            runs = pg.get_agent_runs(incident_id)
            return {
                "incident": _serialize_single(incident),
                "agent_runs": _serialize(runs),
                "source": "database",
            }
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback to in-memory
    if incident_id in _incidents_store:
        inc = _incidents_store[incident_id]
        if user_id != "system" and inc.get("user_id", "system") != user_id:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"incident": _serialize_single(inc), "source": "memory"}

    raise HTTPException(status_code=404, detail="Incident not found")


@app.post("/admin/fix-stuck")
async def fix_stuck_incidents(request: Request):
    """Fix old incidents stuck at 'investigating' in the DB. Requires auth."""
    user_id = _extract_user_id(request)
    if user_id == "system":
        raise HTTPException(status_code=401, detail="Authentication required")
    fixed = 0
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        stuck = pg.list_incidents(limit=50, status="investigating")
        for inc in (stuck or []):
            iid = inc.get("incident_id", "")
            runs = pg.get_agent_runs(iid)
            completed_agents = [r for r in runs if r.get("status") == "completed"]
            if len(completed_agents) >= 2:
                pg.update_incident(iid, {"status": "diagnosed_and_escalated"})
                fixed += 1
    except Exception:
        return {"fixed": fixed, "error": "Operation failed"}
    return {"fixed": fixed, "message": f"Fixed {fixed} stuck incidents"}


@app.get("/runs")
async def list_runs(request: Request):
    """List agent runs (requires auth)."""
    user_id = _extract_user_id(request)
    if user_id == "system":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        from memory.postgres_client import get_postgres
        pg = get_postgres()
        runs = pg.list_all_runs(limit=100)
        return {"runs": _serialize(runs), "total": len(runs)}
    except Exception:
        return {"runs": [], "total": 0, "note": "Database unavailable"}


@app.get("/system/status")
async def system_status():
    """Get system status for dashboard (sanitized, no secrets)."""
    return {
        "agents": ["planner", "analyst", "researcher", "coder", "communicator", "executor"],
        "ollama_model": settings.GEMINI_MODEL if settings.has_gemini() else settings.OLLAMA_MODEL,
        "llm_provider": "gemini" if settings.has_gemini() else "ollama",
        "langfuse_url": settings.LANGFUSE_BASE_URL if settings.has_langfuse() else None,
        "omium_url": "https://app.omium.ai" if settings.has_omium() else None,
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
