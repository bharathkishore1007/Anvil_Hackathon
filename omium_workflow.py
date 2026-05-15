"""
AutoSRE — Omium Workflow Runner
Runs the incident pipeline as an Omium-traced workflow.
"""
import os
import sys
import time

# Add autosre to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "autosre"))

os.environ["OMIUM_API_KEY"] = "omium_qdTsA-tQmGtNEsKxDbg333kCFwFuL16-IRPFhImgRmk"

import omium

omium.init(api_key=os.environ["OMIUM_API_KEY"], project="autosre")


@omium.trace("incident-pipeline")
def run_pipeline(incident_title, incident_severity="high"):
    """Full AutoSRE incident resolution pipeline."""
    result = {
        "incident": incident_title,
        "severity": incident_severity,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Phase 1: Planner
    plan = run_planner(incident_title)
    result["plan"] = plan

    # Phase 2: Parallel agents
    analysis = run_analyst(incident_title)
    research = run_researcher(incident_title)
    result["analysis"] = analysis
    result["research"] = research

    # Phase 3: Executor
    actions = run_executor(incident_title, analysis)
    result["actions"] = actions

    # Phase 4: Communicator
    comms = run_communicator(incident_title, analysis)
    result["communications"] = comms

    result["status"] = "resolved"
    result["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


@omium.trace("agent:planner")
def run_planner(title):
    """Plan the incident resolution."""
    time.sleep(0.5)
    return {
        "tasks": [
            {"agent": "analyst", "input": f"Analyze: {title}"},
            {"agent": "researcher", "input": f"Research: {title}"},
            {"agent": "executor", "input": "Execute remediation"},
            {"agent": "communicator", "input": "Notify stakeholders"},
        ],
        "priority": "P1",
    }


@omium.trace("agent:analyst")
def run_analyst(title):
    """Analyze the incident for root cause."""
    time.sleep(0.5)
    return {
        "root_cause": "NullPointerException in OrderValidator.validate()",
        "confidence": 0.85,
        "affected_services": ["order-service", "payment-gateway"],
    }


@omium.trace("agent:researcher")
def run_researcher(title):
    """Research similar past incidents."""
    time.sleep(0.5)
    return {
        "similar_incidents": 3,
        "recommended_fix": "Increase connection pool size and add null check",
        "documentation_links": ["https://wiki.internal/runbooks/db-pool"],
    }


@omium.trace("agent:executor")
def run_executor(title, analysis):
    """Execute remediation actions."""
    time.sleep(0.5)
    return {
        "github_issue": "Created #142",
        "jira_ticket": "SRE-89",
        "slack_notification": "Sent to #incidents",
    }


@omium.trace("agent:communicator")
def run_communicator(title, analysis):
    """Send notifications and reports."""
    time.sleep(0.5)
    return {
        "email_sent": True,
        "slack_sent": True,
        "report_url": "https://autosre.internal/reports/INC-001",
    }


if __name__ == "__main__":
    print("🚀 Running AutoSRE incident pipeline via Omium...")
    result = run_pipeline(
        "Database connection pool exhausted on payments-api",
        "critical"
    )
    print(f"✅ Pipeline complete: {result['status']}")
    print(f"   Root cause: {result['analysis']['root_cause']}")
    print(f"   Actions: {result['actions']}")
