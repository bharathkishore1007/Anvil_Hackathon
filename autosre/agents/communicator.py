"""
AutoSRE — Communicator Agent
Posts structured incident updates to Slack and sends email summaries.
"""

import logging
from typing import Any, Dict
from agents.base import BaseAgent
from tools.slack_tools import create_incident_thread, post_diagnosis_update, post_resolution_update
from tools.email_tools import send_incident_email

logger = logging.getLogger("autosre.agents.communicator")

COMMUNICATOR_SYSTEM_PROMPT = """You are the Communicator Agent for AutoSRE. You handle all external messaging.

Given incident information and diagnosis results, you must:
1. Post structured incident updates to Slack
2. Format messages with severity, root cause, and actions taken
3. Send email summaries to stakeholders

Respond with JSON:
{
    "actions_taken": ["list of communication actions"],
    "slack_message": {"channel": "...", "status": "posted|simulated"},
    "email_sent": true,
    "summary": "Brief summary of what was communicated"
}
"""


class CommunicatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="communicator", system_prompt=COMMUNICATOR_SYSTEM_PROMPT)

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        logger.info(f"[Communicator] Posting updates for {incident_id}")

        title = input_data.get("title", input_data.get("input", "Incident Update"))
        severity = input_data.get("severity", "medium")
        description = input_data.get("description", input_data.get("input", ""))
        diagnosis = input_data.get("diagnosis", {})

        # 1. Create incident thread in Slack
        thread_result = create_incident_thread(
            incident_id=incident_id or "INC-UNKNOWN",
            title=title,
            severity=severity,
            description=description,
        )

        actions = [f"Slack incident thread: {thread_result.get('status', 'unknown')}"]

        # 2. If we have diagnosis data, post it as a follow-up
        root_cause = diagnosis.get("root_cause", "Under investigation")
        confidence = diagnosis.get("confidence", 0.75)
        recommendation = diagnosis.get("recommendation", "Pending analysis")

        if diagnosis:
            thread_ts = thread_result.get("ts", "")
            post_diagnosis_update(
                thread_ts=thread_ts,
                incident_id=incident_id or "INC-UNKNOWN",
                root_cause=root_cause,
                confidence=confidence,
                recommendation=recommendation,
                similar_incident=diagnosis.get("similar_incident"),
            )
            actions.append("Diagnosis update posted to Slack thread")

        # 3. Send email notification
        email_result = send_incident_email(
            incident_id=incident_id or "INC-UNKNOWN",
            title=title,
            severity=severity,
            root_cause=root_cause,
            confidence=float(confidence) if isinstance(confidence, (int, float)) else 0.75,
            recommendation=recommendation,
        )
        actions.append(f"Email notification: {email_result.get('status', 'unknown')}")

        return {
            "actions_taken": actions,
            "slack_message": thread_result,
            "email_result": email_result,
            "summary": f"Posted to Slack + email for {incident_id}",
            "_meta": {"agent": self.name},
        }
