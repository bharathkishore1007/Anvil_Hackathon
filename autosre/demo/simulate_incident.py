"""
AutoSRE — Incident Simulation Script
Fire a simulated PagerDuty alert and watch the full pipeline execute.

Usage:
    python demo/simulate_incident.py
"""

import httpx
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_URL = os.getenv("AUTOSRE_API_URL", "http://localhost:8000")

DEMO_INCIDENTS = [
    {
        "title": "API error rate spiked to 23% on /checkout endpoint",
        "description": (
            "PagerDuty alert fired — checkout API returning 500 errors at elevated rate. "
            "Error rate exceeded 5% threshold at 23.4%. Started 47 minutes ago after "
            "deployment of PR #4587."
        ),
        "severity": "high",
        "source": "pagerduty",
    },
    {
        "title": "Payment service OOM kills — pods restarting",
        "description": (
            "Kubernetes pods for payment-gateway restarting due to OOM kills. "
            "Memory usage exceeded container limits. Connection pool leak suspected."
        ),
        "severity": "critical",
        "source": "pagerduty",
    },
    {
        "title": "Auth service latency p99 > 2s — login timeouts",
        "description": (
            "Authentication service p99 latency exceeded 2 seconds. "
            "Redis session store may be at max memory with noeviction policy."
        ),
        "severity": "high",
        "source": "slack",
    },
]


def main():
    print("=" * 60)
    print("  AutoSRE — Incident Simulation")
    print("=" * 60)
    print()

    # Check API health
    print("🔍 Checking API health...")
    try:
        health = httpx.get(f"{API_URL}/health", timeout=5.0)
        data = health.json()
        print(f"   API: {'✅' if data['checks']['api'] else '❌'}")
        print(f"   Ollama: {'✅' if data['checks'].get('ollama') else '⚠️  (will use fallbacks)'}")
        print(f"   Redis: {'✅' if data['checks'].get('redis') else '⚠️  (using in-memory)'}")
        print(f"   Postgres: {'✅' if data['checks'].get('postgres') else '⚠️  (using in-memory)'}")
    except Exception as e:
        print(f"   ❌ API unreachable: {e}")
        print(f"   Make sure the gateway is running: python -m gateway.main")
        sys.exit(1)

    print()

    # Pick scenario
    print("Choose a demo scenario:")
    for i, inc in enumerate(DEMO_INCIDENTS, 1):
        print(f"  [{i}] {inc['title'][:60]}...")
    print(f"  [0] All scenarios")
    print()

    choice = input("Enter choice (default: 1): ").strip() or "1"

    if choice == "0":
        selected = DEMO_INCIDENTS
    else:
        idx = int(choice) - 1
        selected = [DEMO_INCIDENTS[idx % len(DEMO_INCIDENTS)]]

    # Fire incidents
    for incident in selected:
        print()
        print(f"🔥 Firing: {incident['title']}")
        print(f"   Severity: {incident['severity'].upper()}")
        print(f"   Source: {incident['source']}")

        try:
            resp = httpx.post(
                f"{API_URL}/incidents/simulate",
                json=incident,
                timeout=10.0,
            )
            data = resp.json()
            inc_id = data.get("incident_id", "unknown")
            print(f"   ✅ Incident created: {inc_id}")
            print(f"   📊 Track at: {API_URL}/incidents/{inc_id}")
            print(f"   🖥️  Dashboard: {API_URL}/")

            # Poll for completion
            print()
            print("   ⏳ Waiting for autonomous resolution...")
            for i in range(60):
                time.sleep(3)
                try:
                    status_resp = httpx.get(f"{API_URL}/incidents/{inc_id}", timeout=5.0)
                    status_data = status_resp.json()
                    inc_status = status_data.get("incident", {}).get("status", "unknown")
                    phase = status_data.get("incident", {}).get("phase", "")

                    sys.stdout.write(f"\r   Status: {inc_status} {phase}{'.' * (i % 4)}   ")
                    sys.stdout.flush()

                    if inc_status in ("diagnosed_and_escalated", "resolved", "failed"):
                        print()
                        print()
                        if inc_status == "failed":
                            print(f"   ❌ Incident processing failed")
                        else:
                            print(f"   ✅ Incident resolved!")
                            root_cause = status_data.get("incident", {}).get("root_cause", "N/A")
                            resolution = status_data.get("incident", {}).get("resolution", "N/A")
                            print(f"   🔍 Root Cause: {root_cause}")
                            print(f"   📝 Resolution: {resolution}")
                        break
                except Exception:
                    pass
            else:
                print("\n   ⚠️  Timed out waiting for resolution. Check the dashboard.")

        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print()
    print("=" * 60)
    print(f"  Dashboard: {API_URL}/")
    print(f"  Incidents: {API_URL}/incidents")
    print(f"  Agent Runs: {API_URL}/runs")
    print("=" * 60)


if __name__ == "__main__":
    main()
