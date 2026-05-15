"""
AutoSRE — Executor Agent
Takes real action: creates GitHub issues, Jira tickets, triggers rollbacks.
"""

import logging
from typing import Any, Dict
from agents.base import BaseAgent
from tools.github_tools import create_issue, trigger_rollback, list_recent_deploys
from tools.jira_tools import create_ticket

logger = logging.getLogger("autosre.agents.executor")

EXECUTOR_SYSTEM_PROMPT = """You are the Executor Agent for AutoSRE. You take real operational actions.

Given incident diagnosis and context, you must:
1. Create a GitHub issue with full incident context
2. Create a Jira ticket for tracking
3. Trigger deployment rollbacks if recommended

Respond with JSON:
{
    "actions_taken": ["list of actions"],
    "github_issue": {"status": "created|simulated", "url": "..."},
    "jira_ticket": {"status": "created|simulated", "key": "..."},
    "rollback": {"status": "triggered|skipped", "reason": "..."}
}
"""


class ExecutorAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="executor", system_prompt=EXECUTOR_SYSTEM_PROMPT)

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        logger.info(f"[Executor] Taking action for {incident_id}")

        title = input_data.get("title", input_data.get("input", "Incident"))
        diagnosis = input_data.get("diagnosis", {})
        root_cause = diagnosis.get("root_cause", "Under investigation")
        recommendation = diagnosis.get("recommendation", "Review required")

        # Build GitHub issue body
        issue_body = f"""## Incident: {incident_id}

**Severity:** {input_data.get('severity', 'high')}
**Root Cause:** {root_cause}
**Confidence:** {diagnosis.get('confidence', 'N/A')}

### Timeline
{diagnosis.get('timeline', 'See agent logs for full timeline.')}

### Recommendation
{recommendation}

### Similar Past Incidents
{self._format_similar(input_data.get('similar_incidents', []))}

---
_Generated automatically by AutoSRE_
"""

        # Create GitHub issue
        gh_result = create_issue(
            title=f"{incident_id}: {title}",
            body=issue_body,
            labels=["incident", "autosre", input_data.get("severity", "high")],
        )

        # Create Jira ticket
        jira_result = create_ticket(
            summary=f"[{incident_id}] {title}",
            description=f"Root Cause: {root_cause}\n\nRecommendation: {recommendation}",
            priority="High" if input_data.get("severity") in ("critical", "high") else "Medium",
            labels=["autosre", "incident"],
        )

        # Check if rollback is recommended
        rollback_result = {"status": "skipped", "reason": "Manual confirmation required"}
        if "rollback" in recommendation.lower() or "revert" in recommendation.lower():
            deploys = list_recent_deploys()
            rollback_result = trigger_rollback(
                deployment_id=deploys.get("deployments", [{}])[0].get("id")
            )

        return {
            "actions_taken": [
                f"GitHub issue: {gh_result.get('status')}",
                f"Jira ticket: {jira_result.get('status')}",
                f"Rollback: {rollback_result.get('status')}",
            ],
            "github_issue": gh_result,
            "jira_ticket": jira_result,
            "rollback": rollback_result,
            "_meta": {"agent": self.name},
        }

    def _format_similar(self, similar: list) -> str:
        if not similar:
            return "_No similar incidents found_"
        lines = []
        for s in similar[:3]:
            lines.append(f"- **{s.get('incident_id', 'N/A')}**: {s.get('title', '')} — {s.get('resolution', 'N/A')}")
        return "\n".join(lines)
