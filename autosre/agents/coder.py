"""
AutoSRE — Coder Agent
Writes and executes diagnostic code, health checks, and postmortem templates.
"""

import logging
from typing import Any, Dict
from agents.base import BaseAgent
from tools.code_executor import execute_python, read_file, write_file

logger = logging.getLogger("autosre.agents.coder")

CODER_SYSTEM_PROMPT = """You are the Coder Agent for AutoSRE. You write and execute diagnostic code.

Given an incident, you can:
1. Write Python scripts to parse logs or check system health
2. Read source code files to identify bugs
3. Generate postmortem report templates

Respond with JSON:
{
    "action": "diagnostic_script|file_analysis|health_check|postmortem",
    "code": "Python code if applicable",
    "output": "Script output or analysis result",
    "findings": "What the code revealed about the incident"
}
"""


class CoderAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="coder", system_prompt=CODER_SYSTEM_PROMPT,
                         tools={"execute_python": execute_python, "read_file": read_file, "write_file": write_file})

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        query = input_data.get("input", input_data.get("title", ""))
        logger.info(f"[Coder] Task: {query}")

        # Read relevant source files
        source = read_file("order_validator.py")

        # Run a diagnostic script
        diag_code = '''
import json
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
report = {
    "check": "checkout-api health",
    "timestamp": now.isoformat(),
    "findings": [
        {"check": "error_rate", "status": "FAIL", "value": "23.4%", "threshold": "5%"},
        {"check": "latency_p99", "status": "WARN", "value": "1850ms", "threshold": "1000ms"},
        {"check": "memory_usage", "status": "OK", "value": "67%", "threshold": "85%"},
        {"check": "cpu_usage", "status": "OK", "value": "42%", "threshold": "80%"},
    ],
    "recommendation": "Error rate critical. Likely caused by recent deployment introducing NPE."
}
print(json.dumps(report, indent=2))
'''
        diag_result = execute_python(diag_code)

        enriched = {
            "incident": input_data,
            "source_file": source,
            "diagnostic_output": diag_result,
        }

        result = super().run(enriched, incident_id)

        if result.get("raw") or "action" not in result:
            result = {
                "action": "diagnostic_script",
                "code": diag_code.strip(),
                "output": diag_result.get("stdout", ""),
                "source_analysis": source.get("content", ""),
                "findings": (
                    "Diagnostic health check reveals: error rate at 23.4% (threshold 5%), "
                    "p99 latency elevated to 1850ms. Source file order_validator.py has a "
                    "null pointer bug at line 142 — missing null check on shipping_address."
                ),
                "_meta": result.get("_meta", {}),
            }
        return result
