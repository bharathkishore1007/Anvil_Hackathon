"""
AutoSRE — PostgreSQL Client
Long-term incident history with connection caching and fast failure.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("autosre.memory.postgres")


class PostgresClient:
    """PostgreSQL client with connection caching and fast-fail when unavailable."""

    def __init__(self):
        self._conn = None
        self._last_fail = 0  # Timestamp of last connection failure
        self._fail_cooldown = 30  # Seconds to wait before retrying after failure

    def _get_conn(self):
        # If connection is open and good, return it
        if self._conn is not None:
            try:
                if not self._conn.closed:
                    return self._conn
            except Exception:
                pass
            self._conn = None

        # Don't retry if we recently failed
        if time.time() - self._last_fail < self._fail_cooldown:
            return None

        try:
            import psycopg
            conninfo = settings.POSTGRES_DSN
            self._conn = psycopg.connect(conninfo, autocommit=True)
            logger.info("Connected to PostgreSQL")
            self._ensure_schema()
            return self._conn
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable: {e}")
            self._conn = None
            self._last_fail = time.time()
            return None

    def _ensure_schema(self):
        """Create tables if they don't exist (safe for Neon/fresh DBs)."""
        if not self._conn:
            return
        try:
            with self._conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS incidents (
                        incident_id TEXT PRIMARY KEY,
                        user_id TEXT DEFAULT 'system',
                        source TEXT DEFAULT 'manual',
                        severity TEXT DEFAULT 'medium',
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        metadata JSONB DEFAULT '{}',
                        status TEXT DEFAULT 'open',
                        execution_plan JSONB,
                        root_cause TEXT,
                        agent_results JSONB,
                        pipeline_duration_ms INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        completed_at TIMESTAMPTZ
                    );
                    CREATE TABLE IF NOT EXISTS agent_runs (
                        run_id TEXT PRIMARY KEY,
                        incident_id TEXT,
                        agent_type TEXT,
                        task_input JSONB,
                        task_output JSONB,
                        status TEXT DEFAULT 'running',
                        started_at TIMESTAMPTZ DEFAULT NOW(),
                        completed_at TIMESTAMPTZ,
                        duration_ms INTEGER DEFAULT 0,
                        token_count INTEGER DEFAULT 0,
                        error TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS tool_calls (
                        call_id TEXT PRIMARY KEY,
                        run_id TEXT,
                        tool_name TEXT,
                        tool_input JSONB,
                        tool_output JSONB,
                        status TEXT DEFAULT 'completed',
                        duration_ms INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)
            # Migration: add user_id if not exists
            try:
                cur.execute("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS user_id TEXT DEFAULT 'system'")
            except Exception:
                pass
            logger.info("PostgreSQL schema verified")
        except Exception as e:
            logger.warning(f"Schema check failed: {e}")

    def create_incident(self, incident: Dict[str, Any]) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO incidents
                       (incident_id, user_id, source, severity, title, description, metadata, status, execution_plan)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (incident_id) DO UPDATE SET
                         status = EXCLUDED.status, updated_at = NOW()""",
                    (incident["incident_id"], incident.get("user_id", "system"),
                     incident.get("source", "manual"),
                     incident.get("severity", "medium"), incident["title"],
                     incident.get("description", ""),
                     json.dumps(incident.get("metadata", {})),
                     incident.get("status", "open"),
                     json.dumps(incident.get("execution_plan")) if incident.get("execution_plan") else None),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to create incident: {e}")
            return False

    def update_incident(self, incident_id: str, updates: Dict[str, Any]) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            set_clauses = []
            values = []
            for key, value in updates.items():
                if key in ("execution_plan", "metadata"):
                    set_clauses.append(f"{key} = %s")
                    values.append(json.dumps(value))
                else:
                    set_clauses.append(f"{key} = %s")
                    values.append(value)
            set_clauses.append("updated_at = NOW()")
            values.append(incident_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE incidents SET {', '.join(set_clauses)} WHERE incident_id = %s",
                    values,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update incident {incident_id}: {e}")
            return False

    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM incidents WHERE incident_id = %s", (incident_id,))
                row = cur.fetchone()
                if row:
                    cols = [desc[0] for desc in cur.description]
                    return dict(zip(cols, row))
            return None
        except Exception as e:
            logger.error(f"Failed to get incident: {e}")
            return None

    def list_incidents(self, limit: int = 50, status: Optional[str] = None) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM incidents WHERE status = %s ORDER BY created_at DESC LIMIT %s", (status, limit))
                else:
                    cur.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT %s", (limit,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list incidents: {e}")
            return []

    def create_agent_run(self, run: Dict[str, Any]) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO agent_runs (run_id, incident_id, agent_type, task_input, status, started_at)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (run_id) DO NOTHING""",
                    (run["run_id"], run["incident_id"], run["agent_type"],
                     json.dumps(run.get("task_input", {})), run.get("status", "running"),
                     datetime.now(timezone.utc)),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to create agent run: {e}")
            return False

    def complete_agent_run(self, run_id: str, output: Any, status: str = "completed",
                           duration_ms: int = 0, token_count: int = 0, error: str = None) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE agent_runs SET task_output = %s, status = %s, completed_at = NOW(),
                       duration_ms = %s, token_count = %s, error = %s WHERE run_id = %s""",
                    (json.dumps(output, default=str), status, duration_ms, token_count, error, run_id),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to complete agent run: {e}")
            return False

    def get_agent_runs(self, incident_id: str) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_runs WHERE incident_id = %s ORDER BY started_at", (incident_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get agent runs: {e}")
            return []

    def list_all_runs(self, limit: int = 100) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT %s", (limit,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            return []

    def log_tool_call(self, call: Dict[str, Any]) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tool_calls (call_id, run_id, tool_name, tool_input, tool_output, status, duration_ms)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (call_id) DO NOTHING""",
                    (call["call_id"], call["run_id"], call["tool_name"],
                     json.dumps(call.get("tool_input", {})),
                     json.dumps(call.get("tool_output", {}), default=str),
                     call.get("status", "completed"), call.get("duration_ms", 0)),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to log tool call: {e}")
            return False

    def get_tool_calls(self, run_id: str) -> List[Dict]:
        conn = self._get_conn()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tool_calls WHERE run_id = %s ORDER BY created_at", (run_id,))
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tool calls: {e}")
            return []

    def ping(self) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass


_pg_client: Optional[PostgresClient] = None

def get_postgres() -> PostgresClient:
    global _pg_client
    if _pg_client is None:
        _pg_client = PostgresClient()
    return _pg_client
