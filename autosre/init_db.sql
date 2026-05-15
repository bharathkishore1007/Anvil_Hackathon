-- AutoSRE Database Initialization
-- Creates tables for incidents, agent runs, tool calls, and vector embeddings

CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Incidents Table ───
CREATE TABLE IF NOT EXISTS incidents (
    id              SERIAL PRIMARY KEY,
    incident_id     VARCHAR(64) UNIQUE NOT NULL,
    source          VARCHAR(32) NOT NULL DEFAULT 'manual',
    severity        VARCHAR(16) NOT NULL DEFAULT 'medium',
    title           TEXT NOT NULL,
    description     TEXT,
    metadata        JSONB DEFAULT '{}',
    status          VARCHAR(32) NOT NULL DEFAULT 'open',
    root_cause      TEXT,
    resolution      TEXT,
    execution_plan  JSONB,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at     TIMESTAMP WITH TIME ZONE,
    embedding       vector(384)
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_embedding ON incidents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);

-- ─── Agent Runs Table ───
CREATE TABLE IF NOT EXISTS agent_runs (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(64) UNIQUE NOT NULL,
    incident_id     VARCHAR(64) REFERENCES incidents(incident_id) ON DELETE CASCADE,
    agent_type      VARCHAR(32) NOT NULL,
    task_input      JSONB,
    task_output     JSONB,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMP WITH TIME ZONE,
    completed_at    TIMESTAMP WITH TIME ZONE,
    duration_ms     INTEGER,
    token_count     INTEGER DEFAULT 0,
    error           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_incident ON agent_runs(incident_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status);

-- ─── Tool Calls Table ───
CREATE TABLE IF NOT EXISTS tool_calls (
    id              SERIAL PRIMARY KEY,
    call_id         VARCHAR(64) UNIQUE NOT NULL,
    run_id          VARCHAR(64) REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    tool_name       VARCHAR(64) NOT NULL,
    tool_input      JSONB,
    tool_output     JSONB,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    duration_ms     INTEGER,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);

-- ─── Seed: Historical Incidents for Similarity Search ───
INSERT INTO incidents (incident_id, source, severity, title, description, status, root_cause, resolution, created_at)
VALUES
    ('INC-2301', 'pagerduty', 'critical', 'Checkout API 500 errors spike',
     'API error rate on /checkout endpoint spiked to 18% after config deploy',
     'resolved', 'Feature flag checkout_v2_enabled was set to true without backend support deployed',
     'Reverted feature flag to false. Full fix deployed in PR #4521.',
     NOW() - INTERVAL '90 days'),

    ('INC-2455', 'github', 'high', 'Payment service OOM kills',
     'Payment microservice pods restarting due to OOM kills after memory leak in connection pool',
     'resolved', 'Connection pool in payment-gateway was not closing idle connections. Max pool size exceeded container memory limit.',
     'Applied connection pool fix in PR #4702. Increased pod memory limit to 2Gi as interim measure.',
     NOW() - INTERVAL '60 days'),

    ('INC-2510', 'pagerduty', 'critical', 'Database replication lag > 30s',
     'Primary-replica lag on orders-db exceeded 30 seconds causing stale reads',
     'resolved', 'Long-running analytical query on replica caused lock contention. Query originated from a new reporting dashboard.',
     'Killed the long-running query. Added query timeout of 30s on replica. Moved reporting to dedicated read replica.',
     NOW() - INTERVAL '45 days'),

    ('INC-2678', 'slack', 'medium', 'CDN cache miss rate elevated',
     'Cache miss rate on CDN increased from 5% to 35% after cache purge',
     'resolved', 'Automated cache purge job ran with incorrect scope — purged all paths instead of /static/* only.',
     'Fixed purge job scope. Cache warmed back up within 20 minutes. Added scope validation to purge API.',
     NOW() - INTERVAL '30 days'),

    ('INC-2799', 'pagerduty', 'high', 'Auth service latency p99 > 2s',
     'Authentication service p99 latency exceeded 2 seconds, causing login timeouts',
     'resolved', 'Redis session store reached max memory. Eviction policy was set to noeviction causing blocking.',
     'Changed Redis eviction policy to allkeys-lru. Increased maxmemory to 4GB. Added monitoring alert for memory usage > 80%.',
     NOW() - INTERVAL '15 days')
ON CONFLICT (incident_id) DO NOTHING;
