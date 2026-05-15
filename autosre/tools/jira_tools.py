"""
AutoSRE — Jira Tools
Create and manage Jira tickets for incident tracking.
"""

import logging
from typing import Any, Dict, List
from config import settings

logger = logging.getLogger("autosre.tools.jira")


def _get_jira_client():
    if not settings.has_jira():
        return None
    try:
        from jira import JIRA
        base_url = settings.JIRA_URL.split("?")[0].rstrip("/")
        return JIRA(server=base_url, basic_auth=(settings.JIRA_EMAIL, settings.JIRA_API_TOKEN))
    except Exception as e:
        logger.warning(f"Jira client init failed: {e}")
        return None


def create_ticket(summary: str, description: str, issue_type: str = "Bug",
                  priority: str = "High", labels: List[str] = None,
                  project_key: str = None) -> Dict[str, Any]:
    project = project_key or settings.JIRA_PROJECT_KEY
    labels = labels or ["autosre", "incident"]
    logger.info(f"[jira] Creating ticket: {summary}")

    client = _get_jira_client()
    if client:
        try:
            fields = {
                "project": {"key": project},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
                "labels": labels,
            }
            issue = client.create_issue(fields=fields)
            return {"status": "created", "key": issue.key, "url": f"{settings.JIRA_URL.split('?')[0].rstrip('/')}/browse/{issue.key}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    return {"status": "simulated", "key": f"{project}-9999", "summary": summary, "note": "Jira simulated"}
