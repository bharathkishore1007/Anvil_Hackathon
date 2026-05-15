import httpx, json
r = httpx.get('https://autosre-239243701215.asia-south1.run.app/incidents/INC-CED56E', timeout=15)
d = r.json()
inc = d.get('incident', {})
print("Status:", inc.get('status'))
print("Agent Results:", list(inc.get('agent_results', {}).keys()) if inc.get('agent_results') else 'None')
runs = d.get('agent_runs', [])
print(f"Total runs: {len(runs)}")
for run in runs:
    print(f"  {run['agent_type']}: {run['status']} | {run.get('duration_ms', 0)}ms | error={run.get('error', 'None')}")
