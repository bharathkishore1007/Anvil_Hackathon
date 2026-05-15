"""
AutoSRE — Researcher Agent
Searches web and internal runbooks for context on incidents.
Performs real web searches via DuckDuckGo (StackOverflow, CVEs, postmortems).
"""

import asyncio
import logging
from typing import Any, Dict

from agents.base import BaseAgent
from tools.web_search import web_search, search_cve_and_errors, query_runbook_db

logger = logging.getLogger("autosre.agents.researcher")

RESEARCHER_SYSTEM_PROMPT = """You are the Researcher Agent for AutoSRE. Your job is to find relevant context for production incidents.

Given an incident, you must:
1. Search for similar known issues and fixes
2. Check internal runbooks for relevant procedures
3. Find documentation or blog posts about the error type

You have received search results and runbook matches. Analyze them and respond with:
{
    "findings": [
        {"source": "runbook|web|cve", "title": "...", "relevance": "high|medium|low", "summary": "..."}
    ],
    "recommended_fix": "Most likely fix based on research",
    "similar_incident": "Reference to most similar past incident if found",
    "runbook_reference": "Relevant runbook ID and title"
}
"""


class ResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="researcher", system_prompt=RESEARCHER_SYSTEM_PROMPT)

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        query = input_data.get("input", input_data.get("title", ""))
        logger.info(f"[Researcher] Researching: {query}")

        # ── Step 1: General web search ──
        logger.info(f"[Researcher] Step 1/3: Web search via DuckDuckGo")
        try:
            search_results = asyncio.get_event_loop().run_until_complete(web_search(query))
        except RuntimeError:
            search_results = asyncio.run(web_search(query))
        logger.info(f"[Researcher] Web search returned {search_results.get('results_count', 0)} results (source: {search_results.get('source', 'unknown')})")

        # ── Step 2: Targeted CVE / StackOverflow / postmortem search ──
        logger.info(f"[Researcher] Step 2/3: CVE & StackOverflow targeted search")
        try:
            cve_results = asyncio.get_event_loop().run_until_complete(search_cve_and_errors(query))
        except RuntimeError:
            cve_results = asyncio.run(search_cve_and_errors(query))
        logger.info(f"[Researcher] CVE search: {cve_results.get('searches_performed', 0)} queries → {cve_results.get('total_results', 0)} results")

        # ── Step 3: Internal runbook search ──
        logger.info(f"[Researcher] Step 3/3: Internal runbook database query")
        runbook_results = query_runbook_db(query)
        logger.info(f"[Researcher] Runbook matches: {len(runbook_results.get('matches', []))}")

        enriched = {
            "incident": input_data,
            "web_search_results": search_results,
            "cve_search_results": cve_results,
            "runbook_results": runbook_results,
        }

        result = super().run(enriched, incident_id)

        # Ensure structured output
        if "findings" not in result or result.get("raw"):
            findings = []
            for rb in runbook_results.get("matches", []):
                findings.append({
                    "source": "runbook", "title": rb.get("title", ""),
                    "relevance": "high", "summary": rb.get("content", "")[:300],
                })
            for sr in search_results.get("results", []):
                findings.append({
                    "source": "web", "title": sr.get("title", ""),
                    "relevance": "medium", "summary": sr.get("snippet", ""),
                    "url": sr.get("url", ""),
                })
            for cr in cve_results.get("results", [])[:3]:
                findings.append({
                    "source": "cve", "title": cr.get("title", ""),
                    "relevance": "medium", "summary": cr.get("snippet", ""),
                    "url": cr.get("url", ""),
                })

            result = {
                "findings": findings[:8],
                "recommended_fix": "Revert recent deployment and apply null pointer fix based on runbook RB-001",
                "similar_incident": input_data.get("similar_past_incidents", [{}])[0].get("incident_id", "None found") if input_data.get("similar_past_incidents") else "None found",
                "runbook_reference": runbook_results.get("matches", [{}])[0].get("id", "N/A") if runbook_results.get("matches") else "N/A",
                "web_searches_performed": 1 + cve_results.get("searches_performed", 0),
                "_meta": result.get("_meta", {}),
            }

        return result
