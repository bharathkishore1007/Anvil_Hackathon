"""
AutoSRE — Web Search Tool
HTTP-based web search and URL content fetching.
Uses DuckDuckGo HTML search as a free, no-API-key search backend.
"""

import logging
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("autosre.tools.web_search")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


async def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web for information related to an incident.

    Returns structured results with titles, snippets, and URLs.
    """
    logger.info(f"[web_search] Searching DuckDuckGo: {query}")
    results = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Use DuckDuckGo HTML search
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=HEADERS,
                follow_redirects=True,
            )
            logger.info(f"[web_search] DuckDuckGo response: HTTP {resp.status_code}, {len(resp.text)} bytes")

            if resp.status_code == 200:
                text = resp.text
                # Parse basic results from HTML
                snippets = re.findall(
                    r'class="result__snippet"[^>]*>(.*?)</a>',
                    text, re.DOTALL
                )
                titles = re.findall(
                    r'class="result__a"[^>]*>(.*?)</a>',
                    text, re.DOTALL
                )
                urls = re.findall(
                    r'class="result__url"[^>]*>(.*?)</a>',
                    text, re.DOTALL
                )

                for i in range(min(max_results, len(titles))):
                    clean_title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else ""
                    clean_snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                    clean_url = re.sub(r'<[^>]+>', '', urls[i]).strip() if i < len(urls) else ""
                    results.append({
                        "title": clean_title,
                        "snippet": clean_snippet,
                        "url": clean_url,
                    })
                    logger.info(f"[web_search] Result {i+1}: {clean_title[:80]}")
    except Exception as e:
        logger.warning(f"[web_search] DuckDuckGo search failed: {e}")

    # If no results from web, provide structured knowledge base results
    if not results:
        logger.info("[web_search] No web results, using internal knowledge base fallback")
        results = _knowledge_base_search(query)

    logger.info(f"[web_search] Total results: {len(results)} for query: {query[:60]}")
    return {
        "query": query,
        "results_count": len(results),
        "source": "duckduckgo" if results and results[0].get("url", "").startswith("http") else "knowledge_base",
        "results": results,
    }


async def search_cve_and_errors(incident_title: str) -> Dict[str, Any]:
    """Targeted search for CVEs, Stack Overflow issues, and known bug reports.

    This performs multiple focused web searches to find actionable remediation context.
    """
    logger.info(f"[cve_search] Running targeted CVE/error searches for: {incident_title}")

    # Extract key error terms
    error_terms = _extract_error_terms(incident_title)

    searches = [
        f"site:stackoverflow.com {error_terms} production fix",
        f"CVE {error_terms} vulnerability remediation",
        f"{error_terms} incident postmortem root cause",
    ]

    all_results = []
    for search_query in searches:
        result = await web_search(search_query, max_results=3)
        for r in result.get("results", []):
            r["search_category"] = search_query.split(" ")[0]  # site:, CVE, or error term
        all_results.extend(result.get("results", []))
        logger.info(f"[cve_search] '{search_query[:50]}' → {result['results_count']} results")

    return {
        "query": incident_title,
        "searches_performed": len(searches),
        "total_results": len(all_results),
        "results": all_results[:8],
    }


def _extract_error_terms(title: str) -> str:
    """Extract meaningful error terms from incident title for targeted searching."""
    # Remove common SRE noise words
    noise = {"the", "a", "an", "on", "in", "to", "for", "is", "was", "are", "been",
             "has", "had", "have", "test", "inc", "alert", "fired", "triggered"}
    words = [w for w in re.split(r'[\s\-_/]+', title.lower()) if w not in noise and len(w) > 2]
    return " ".join(words[:6])


async def fetch_url(url: str) -> Dict[str, Any]:
    """Fetch and extract text content from a URL."""
    logger.info(f"[fetch_url] Fetching: {url}")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
            text = resp.text
            # Strip HTML tags for plain text
            clean = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
            clean = re.sub(r'<[^>]+>', ' ', clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return {
                "url": url,
                "status_code": resp.status_code,
                "content": clean[:5000],
                "content_length": len(clean),
            }
    except Exception as e:
        return {"url": url, "error": str(e)}


def query_runbook_db(query: str) -> Dict[str, Any]:
    """Search internal runbook database (simulated with realistic SRE runbooks)."""
    logger.info(f"[query_runbook_db] Searching runbooks: {query}")

    runbooks = [
        {
            "id": "RB-001",
            "title": "API Error Rate Spike Runbook",
            "content": (
                "1. Check deployment timeline — did a new version ship in last 2 hours?\n"
                "2. Query error logs: kubectl logs -l app=api --tail=500 | grep ERROR\n"
                "3. Check if error is 500 (server) or 4xx (client) — different root causes.\n"
                "4. If 500: check for null pointer / unhandled exceptions in recent commits.\n"
                "5. If new deploy: consider immediate rollback.\n"
                "6. Escalate to on-call backend engineer if not resolved in 15 minutes."
            ),
            "tags": ["api", "error", "500", "rate", "spike"],
        },
        {
            "id": "RB-002",
            "title": "Database Replication Lag Runbook",
            "content": (
                "1. Check replica status: SELECT * FROM pg_stat_replication;\n"
                "2. Look for long-running queries on replica: SELECT * FROM pg_stat_activity WHERE state = 'active';\n"
                "3. Kill any analytical queries blocking replication.\n"
                "4. Check disk I/O on replica — may need larger instance.\n"
                "5. If lag > 60s: failover to secondary replica."
            ),
            "tags": ["database", "replication", "lag", "postgres"],
        },
        {
            "id": "RB-003",
            "title": "Memory/OOM Kill Runbook",
            "content": (
                "1. Check pod restarts: kubectl get pods | grep CrashLoopBackOff\n"
                "2. Check memory usage trend: kubectl top pods\n"
                "3. Common causes: connection pool leak, unbounded cache, large payload processing.\n"
                "4. Immediate fix: increase memory limits in deployment manifest.\n"
                "5. Long-term: profile memory allocation and fix the leak."
            ),
            "tags": ["memory", "oom", "crash", "pod", "restart"],
        },
        {
            "id": "RB-004",
            "title": "Auth Service Latency Runbook",
            "content": (
                "1. Check Redis session store memory: redis-cli INFO memory\n"
                "2. Check Redis eviction policy: CONFIG GET maxmemory-policy\n"
                "3. If noeviction + maxmemory reached: change to allkeys-lru.\n"
                "4. Check for connection pool exhaustion in auth service.\n"
                "5. Consider adding Redis Cluster if single node is bottleneck."
            ),
            "tags": ["auth", "latency", "redis", "session", "login"],
        },
    ]

    query_lower = query.lower()
    matches = []
    for rb in runbooks:
        score = sum(1 for tag in rb["tags"] if tag in query_lower)
        if score > 0 or any(word in rb["title"].lower() for word in query_lower.split()):
            matches.append({**rb, "relevance_score": score})

    matches.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return {
        "query": query,
        "matches": matches[:3],
        "total_runbooks": len(runbooks),
    }


def _knowledge_base_search(query: str) -> List[Dict]:
    """Internal knowledge base fallback for web search."""
    query_lower = query.lower()
    kb = [
        {
            "title": "Common API Error Rate Causes",
            "snippet": "API error rate spikes are commonly caused by: 1) Bad deployments introducing null pointer exceptions, 2) Database connection pool exhaustion, 3) Upstream service failures, 4) Configuration changes (feature flags).",
            "url": "internal://kb/api-errors",
        },
        {
            "title": "Deployment Rollback Best Practices",
            "snippet": "When error rates spike after deployment: verify deployment timeline, check for breaking changes in recent PRs, use canary analysis, and prefer automated rollback within 5 minutes of detection.",
            "url": "internal://kb/rollback",
        },
        {
            "title": "Null Pointer Exception Patterns",
            "snippet": "Null pointer exceptions in production often result from: 1) Missing null checks on API responses, 2) Database records with unexpected NULL fields, 3) Race conditions in initialization.",
            "url": "internal://kb/npe-patterns",
        },
    ]
    return [item for item in kb if any(word in item["title"].lower() or word in item["snippet"].lower() for word in query_lower.split()[:3])][:3]
