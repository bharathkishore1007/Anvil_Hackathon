"""
AutoSRE — Event Normalizer
Converts raw webhook payloads from PagerDuty, GitHub, and Slack
into a standard IncidentEvent envelope.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class IncidentEvent(BaseModel):
    """Standard incident event envelope used throughout the system."""
    incident_id: str = Field(default_factory=lambda: f"INC-{uuid.uuid4().hex[:6].upper()}")
    source: str = "manual"
    severity: str = "medium"
    title: str
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "open"


def normalize_pagerduty(payload: Dict[str, Any]) -> IncidentEvent:
    """Convert a PagerDuty webhook payload into a standard IncidentEvent."""
    event = payload.get("event", payload)
    data = event.get("data", event)

    severity_map = {"critical": "critical", "error": "high", "warning": "medium", "info": "low"}
    raw_severity = data.get("severity", data.get("urgency", "medium"))

    return IncidentEvent(
        incident_id=f"INC-{data.get('id', uuid.uuid4().hex[:6]).upper()[:6]}",
        source="pagerduty",
        severity=severity_map.get(raw_severity, "medium"),
        title=data.get("title", data.get("summary", "PagerDuty Alert")),
        description=data.get("description", data.get("details", {}).get("body", "")),
        metadata={
            "service": data.get("service", {}).get("name", "unknown"),
            "escalation_policy": data.get("escalation_policy", {}).get("name", ""),
            "html_url": data.get("html_url", ""),
            "raw_event_type": event.get("event_type", ""),
        },
    )


def normalize_github(payload: Dict[str, Any]) -> IncidentEvent:
    """Convert a GitHub webhook payload into a standard IncidentEvent."""
    action = payload.get("action", "")
    alert = payload.get("alert", {})
    repo = payload.get("repository", {})

    # Handle different GitHub event types
    if "alert" in payload:
        title = alert.get("title", f"GitHub Alert: {action}")
        description = alert.get("body", alert.get("text", ""))
        severity = "high"
    elif "deployment_status" in payload:
        ds = payload["deployment_status"]
        title = f"Deployment {ds.get('state', 'unknown')} — {repo.get('full_name', '')}"
        description = ds.get("description", "")
        severity = "critical" if ds.get("state") == "failure" else "medium"
    else:
        title = f"GitHub Event: {action} on {repo.get('full_name', 'unknown')}"
        description = payload.get("description", "")
        severity = "medium"

    return IncidentEvent(
        source="github",
        severity=severity,
        title=title,
        description=description,
        metadata={
            "repository": repo.get("full_name", ""),
            "action": action,
            "sender": payload.get("sender", {}).get("login", ""),
            "html_url": repo.get("html_url", ""),
        },
    )


def normalize_slack(payload: Dict[str, Any]) -> IncidentEvent:
    """Convert a Slack slash command or event payload into a standard IncidentEvent."""
    text = payload.get("text", "")
    user = payload.get("user_name", payload.get("user", {}).get("name", "unknown"))

    # Parse severity from text if present
    severity = "medium"
    for sev in ["critical", "high", "low"]:
        if sev in text.lower():
            severity = sev
            text = text.replace(sev, "").strip()
            break

    return IncidentEvent(
        source="slack",
        severity=severity,
        title=text or "Slack-reported incident",
        description=f"Reported by @{user} via Slack command",
        metadata={
            "reporter": user,
            "channel": payload.get("channel_name", payload.get("channel", "")),
            "command": payload.get("command", ""),
        },
    )


def normalize_manual(payload: Dict[str, Any]) -> IncidentEvent:
    """Convert a manual simulation payload into a standard IncidentEvent."""
    inc_id = payload.get("incident_id") or f"INC-{uuid.uuid4().hex[:6].upper()}"
    return IncidentEvent(
        incident_id=inc_id,
        source=payload.get("source", "manual"),
        severity=payload.get("severity", "high"),
        title=payload.get("title", "Simulated Incident"),
        description=payload.get("description", ""),
        metadata=payload.get("metadata", {}),
    )
