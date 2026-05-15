"""
AutoSRE — Celery Task Definitions
Defines the async tasks that power the incident resolution pipeline.
"""

import json
import logging
import time
from typing import Any, Dict

from taskqueue.celery_app import celery_app

logger = logging.getLogger("autosre.queue.tasks")


@celery_app.task(bind=True, name="process_incident", max_retries=3,
                 default_retry_delay=5, queue="high")
def process_incident(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
    """Main task: orchestrate the full incident resolution pipeline.
    
    1. Planner creates execution plan
    2. Independent agents run in parallel
    3. Dependent agents wait for prerequisites
    4. Results are aggregated
    """
    from agents.planner import PlannerAgent
    from memory.redis_client import get_redis
    from memory.postgres_client import get_postgres

    incident_id = incident_data.get("incident_id", "INC-UNKNOWN")
    logger.info(f"[Task] Processing incident {incident_id}")

    redis = get_redis()
    pg = get_postgres()

    try:
        # Store incident in DB
        pg.create_incident(incident_data)
        redis.add_active_incident(incident_id)
        redis.set_incident_state(incident_id, {
            "status": "processing",
            "phase": "planning",
            **incident_data,
        })
        redis.publish_incident_update(incident_id, "started", incident_data)

        # Phase 1: Planning
        planner = PlannerAgent()
        plan = planner.create_plan(incident_data)

        redis.store_execution_plan(incident_id, plan)
        pg.update_incident(incident_id, {"execution_plan": plan, "status": "investigating"})
        redis.publish_incident_update(incident_id, "plan_created", plan)

        # Phase 2: Execute tasks (respecting dependencies)
        results = _execute_plan(incident_id, plan, incident_data)

        # Phase 3: Aggregate results
        final = planner.aggregate_results(incident_id, plan, results)

        # Update state
        pg.update_incident(incident_id, {
            "status": "diagnosed_and_escalated",
            "root_cause": final.get("root_cause", ""),
            "resolution": final.get("summary", ""),
        })
        redis.update_incident_field(incident_id, "status", "diagnosed_and_escalated")
        redis.publish_incident_update(incident_id, "resolved", final)

        logger.info(f"[Task] Incident {incident_id} fully processed")
        return final

    except Exception as e:
        logger.error(f"[Task] Failed to process {incident_id}: {e}")
        redis.update_incident_field(incident_id, "status", "failed")
        redis.publish_incident_update(incident_id, "error", {"error": str(e)})
        raise self.retry(exc=e) if self.request.retries < self.max_retries else None


def _execute_plan(incident_id: str, plan: Dict, incident_data: Dict) -> Dict[str, Any]:
    """Execute the task plan respecting dependencies."""
    from agents.analyst import AnalystAgent
    from agents.researcher import ResearcherAgent
    from agents.coder import CoderAgent
    from agents.communicator import CommunicatorAgent
    from agents.executor import ExecutorAgent
    from memory.redis_client import get_redis

    redis = get_redis()
    tasks = plan.get("tasks", [])
    results = {}
    completed = set()

    agent_map = {
        "analyst": AnalystAgent,
        "researcher": ResearcherAgent,
        "coder": CoderAgent,
        "communicator": CommunicatorAgent,
        "executor": ExecutorAgent,
    }

    # Simple dependency-respecting execution
    max_iterations = len(tasks) * 2
    iteration = 0

    while len(completed) < len(tasks) and iteration < max_iterations:
        iteration += 1
        for task in tasks:
            task_id = task["id"]
            if task_id in completed:
                continue

            # Check dependencies
            deps = task.get("depends_on", [])
            if not all(d in completed for d in deps):
                continue

            agent_type = task.get("agent", "analyst")
            logger.info(f"[Plan] Executing {task_id} → {agent_type}")

            redis.set_task_status(incident_id, task_id, "running")
            redis.publish_incident_update(incident_id, "task_started", {
                "task_id": task_id, "agent": agent_type,
            })

            # Build agent input
            agent_input = {
                "input": task.get("input", ""),
                "title": incident_data.get("title", ""),
                "severity": incident_data.get("severity", "medium"),
                "description": incident_data.get("description", ""),
                "incident_id": incident_id,
            }

            # Add dependency results to input
            for dep_id in deps:
                dep_task = next((t for t in tasks if t["id"] == dep_id), None)
                if dep_task and dep_task.get("agent") in results:
                    agent_input["diagnosis"] = results[dep_task["agent"]]

            # Add similar incidents
            agent_input["similar_incidents"] = plan.get("similar_incidents", [])

            # Execute agent
            try:
                agent_class = agent_map.get(agent_type)
                if agent_class:
                    agent = agent_class()
                    result = agent.run(agent_input, incident_id)
                    results[agent_type] = result
                    redis.set_task_status(incident_id, task_id, "completed", result)
                    redis.publish_incident_update(incident_id, "task_completed", {
                        "task_id": task_id, "agent": agent_type,
                        "result_preview": str(result)[:200],
                    })
                else:
                    logger.warning(f"Unknown agent type: {agent_type}")
                    redis.set_task_status(incident_id, task_id, "skipped")
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                redis.set_task_status(incident_id, task_id, "failed", {"error": str(e)})
                results[agent_type] = {"error": str(e)}

            completed.add(task_id)

    return results


@celery_app.task(name="run_agent_task", max_retries=2)
def run_agent_task(agent_type: str, input_data: Dict, incident_id: str) -> Dict[str, Any]:
    """Run a single agent task (used for individual dispatching)."""
    from agents.analyst import AnalystAgent
    from agents.researcher import ResearcherAgent
    from agents.coder import CoderAgent
    from agents.communicator import CommunicatorAgent
    from agents.executor import ExecutorAgent

    agent_map = {
        "analyst": AnalystAgent,
        "researcher": ResearcherAgent,
        "coder": CoderAgent,
        "communicator": CommunicatorAgent,
        "executor": ExecutorAgent,
    }

    agent_class = agent_map.get(agent_type)
    if not agent_class:
        return {"error": f"Unknown agent: {agent_type}"}

    agent = agent_class()
    return agent.run(input_data, incident_id)
