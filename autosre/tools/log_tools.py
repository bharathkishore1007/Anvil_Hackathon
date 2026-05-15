"""
AutoSRE — Log Analysis & Metrics Tools
Parse logs, query metrics, and correlate events for incident diagnosis.
Uses realistic simulated data for demo purposes.
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger("autosre.tools.log_tools")


def parse_logs(query: str, timeframe: str = "1h", service: str = "api") -> Dict[str, Any]:
    """Parse and analyze log data for a service. Returns structured findings."""
    logger.info(f"[parse_logs] Analyzing {service} logs for: {query} (last {timeframe})")
    now = datetime.now(timezone.utc)

    log_entries = [
        {"timestamp": (now - timedelta(minutes=47)).isoformat(), "level": "ERROR",
         "service": "checkout-api", "message": "NullPointerException in OrderValidator.validate()",
         "trace_id": "abc-123-def", "stack_trace": "at com.api.OrderValidator.validate(OrderValidator.py:142)\n  at com.api.CheckoutHandler.process(CheckoutHandler.py:89)"},
        {"timestamp": (now - timedelta(minutes=46)).isoformat(), "level": "ERROR",
         "service": "checkout-api", "message": "NullPointerException in OrderValidator.validate()",
         "trace_id": "ghi-456-jkl", "stack_trace": "at com.api.OrderValidator.validate(OrderValidator.py:142)"},
        {"timestamp": (now - timedelta(minutes=45)).isoformat(), "level": "WARN",
         "service": "checkout-api", "message": "High error rate detected: 23% (threshold: 5%)",
         "trace_id": "mno-789-pqr"},
        {"timestamp": (now - timedelta(minutes=44)).isoformat(), "level": "ERROR",
         "service": "checkout-api", "message": "Failed to process order: order.shipping_address is None",
         "trace_id": "stu-012-vwx"},
        {"timestamp": (now - timedelta(minutes=43)).isoformat(), "level": "INFO",
         "service": "deploy-bot", "message": "Deployment completed: PR #4587 (a1b2c3d) → production",
         "trace_id": "deploy-4587"},
    ]

    return {
        "service": service,
        "timeframe": timeframe,
        "total_entries": len(log_entries),
        "error_count": sum(1 for e in log_entries if e["level"] == "ERROR"),
        "first_error_at": log_entries[0]["timestamp"],
        "log_entries": log_entries,
        "analysis": {
            "primary_error": "NullPointerException in OrderValidator.validate()",
            "error_file": "OrderValidator.py:142",
            "related_deployment": "PR #4587 deployed 47 minutes ago",
            "pattern": "Errors started immediately after deployment a1b2c3d",
        },
    }


def query_metrics_api(metric: str, service: str = "checkout-api", timeframe: str = "1h") -> Dict[str, Any]:
    """Query metrics for a service — returns time-series data."""
    logger.info(f"[query_metrics] {metric} for {service} (last {timeframe})")
    now = datetime.now(timezone.utc)

    if "error" in metric.lower():
        data_points = [
            {"time": (now - timedelta(minutes=60)).isoformat(), "value": 0.5},
            {"time": (now - timedelta(minutes=50)).isoformat(), "value": 0.8},
            {"time": (now - timedelta(minutes=47)).isoformat(), "value": 5.2},
            {"time": (now - timedelta(minutes=45)).isoformat(), "value": 18.7},
            {"time": (now - timedelta(minutes=40)).isoformat(), "value": 23.1},
            {"time": (now - timedelta(minutes=30)).isoformat(), "value": 22.8},
            {"time": (now - timedelta(minutes=20)).isoformat(), "value": 23.4},
        ]
        return {"metric": metric, "service": service, "unit": "percent",
                "current_value": 23.4, "threshold": 5.0, "data_points": data_points,
                "anomaly_detected": True, "anomaly_start": (now - timedelta(minutes=47)).isoformat()}
    elif "latency" in metric.lower():
        return {"metric": metric, "service": service, "unit": "ms",
                "current_value": 1850, "threshold": 1000, "p50": 450, "p95": 1200, "p99": 1850,
                "anomaly_detected": True}
    else:
        return {"metric": metric, "service": service, "unit": "count",
                "current_value": random.randint(100, 5000), "threshold": None}


def correlate_events(incident_title: str, timeframe: str = "2h") -> Dict[str, Any]:
    """Correlate events across services around the incident time."""
    logger.info(f"[correlate_events] Correlating events for: {incident_title}")
    now = datetime.now(timezone.utc)

    return {
        "correlated_events": [
            {"time": (now - timedelta(minutes=50)).isoformat(), "source": "ci/cd",
             "event": "Build #8847 completed — PR #4587 merged to main", "relevance": "high"},
            {"time": (now - timedelta(minutes=48)).isoformat(), "source": "kubernetes",
             "event": "Rolling update started for checkout-api deployment", "relevance": "high"},
            {"time": (now - timedelta(minutes=47)).isoformat(), "source": "kubernetes",
             "event": "New pods healthy — checkout-api-v2-a1b2c3d (3/3 ready)", "relevance": "high"},
            {"time": (now - timedelta(minutes=47)).isoformat(), "source": "monitoring",
             "event": "Error rate anomaly detected on /checkout endpoint", "relevance": "critical"},
            {"time": (now - timedelta(minutes=45)).isoformat(), "source": "pagerduty",
             "event": "Alert fired: API error rate > 5% on checkout-api", "relevance": "critical"},
        ],
        "timeline_summary": "Deployment of PR #4587 at T-50min triggered error rate spike at T-47min. "
                          "Strong correlation between deploy and error onset.",
        "likely_trigger": "Deployment of PR #4587 (commit a1b2c3d)",
    }
