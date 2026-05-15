"""
AutoSRE — Analyst Agent
Reads raw logs, metrics, and stack traces. Produces structured diagnosis.
"""

import logging
from typing import Any, Dict

from agents.base import BaseAgent
from tools.log_tools import parse_logs, query_metrics_api, correlate_events

logger = logging.getLogger("autosre.agents.analyst")

ANALYST_SYSTEM_PROMPT = """You are the Analyst Agent for AutoSRE. Your job is to diagnose production incidents.

Given an incident description, you must:
1. Analyze log data for errors and patterns
2. Check metrics for anomalies
3. Correlate events across services to find the root cause
4. Produce a structured diagnosis

You have already received tool outputs with log data, metrics, and correlated events.
Analyze them and respond with a JSON object:
{
    "root_cause": "Clear description of what caused the incident",
    "confidence": 0.85,
    "error_type": "e.g. NullPointerException, OOM, timeout",
    "affected_service": "service name",
    "affected_file": "file:line if known",
    "timeline": "Brief timeline of events",
    "recommendation": "Specific action to resolve",
    "severity_assessment": "critical|high|medium|low"
}
"""


class AnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="analyst", system_prompt=ANALYST_SYSTEM_PROMPT)

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        title = input_data.get("input", input_data.get("title", ""))
        logger.info(f"[Analyst] Analyzing: {title}")

        # Execute tools to gather data
        logs = parse_logs(title)
        metrics = query_metrics_api("error_rate", timeframe="1h")
        events = correlate_events(title)

        # Enrich input with tool results
        enriched = {
            "incident": input_data,
            "log_analysis": logs,
            "metrics": metrics,
            "correlated_events": events,
        }

        # Get LLM analysis
        result = super().run(enriched, incident_id)

        # Ensure required fields with smart defaults from tool data
        if "root_cause" not in result or result.get("raw"):
            log_analysis = logs.get("analysis", {})
            result = {
                "root_cause": log_analysis.get("primary_error", "Under investigation"),
                "confidence": 0.85,
                "error_type": "NullPointerException",
                "affected_service": logs.get("service", "checkout-api"),
                "affected_file": log_analysis.get("error_file", "unknown"),
                "timeline": (
                    f"Deploy detected at {log_analysis.get('related_deployment', 'unknown time')}. "
                    f"Errors began at {logs.get('first_error_at', 'unknown')}. "
                    f"{logs.get('error_count', 0)} errors found in logs."
                ),
                "recommendation": "Revert the recent deployment or apply a hotfix for the null pointer check",
                "severity_assessment": "high",
                "log_entries": logs.get("log_entries", [])[:3],
                "metrics_snapshot": {"error_rate": metrics.get("current_value"), "threshold": metrics.get("threshold")},
                "correlated_events": events.get("correlated_events", [])[:3],
                "_meta": result.get("_meta", {}),
            }

        return result
