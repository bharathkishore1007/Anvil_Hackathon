"""
AutoSRE — Redis Client
Short-term state management with graceful fallback when Redis is unavailable.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("autosre.memory.redis")


class RedisClient:
    """Redis-backed short-term state. All methods silently fail if Redis is down."""

    def __init__(self):
        self._client = None
        try:
            import redis
            url = settings.REDIS_URL
            # Upstash uses rediss:// (TLS)
            ssl = url.startswith("rediss://")
            kwargs = dict(decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
            if ssl:
                import ssl as ssl_mod
                kwargs["ssl_cert_reqs"] = ssl_mod.CERT_NONE
            self._client = redis.Redis.from_url(url, **kwargs)
            self._client.ping()
            logger.info(f"Redis connected {'(TLS)' if ssl else ''}")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e} — using in-memory fallback")
            self._client = None
        self._mem: Dict[str, Any] = {}

    def _safe(self, fn, fallback=None):
        if not self._client:
            return fallback
        try:
            return fn()
        except Exception:
            return fallback

    def set_incident_state(self, incident_id: str, state: Dict[str, Any], ttl: int = 3600):
        self._mem[f"incident:{incident_id}"] = state
        self._safe(lambda: self._client.setex(f"incident:{incident_id}", ttl, json.dumps(state, default=str)))

    def get_incident_state(self, incident_id: str) -> Optional[Dict[str, Any]]:
        mem = self._mem.get(f"incident:{incident_id}")
        if mem:
            return mem
        data = self._safe(lambda: self._client.get(f"incident:{incident_id}"))
        return json.loads(data) if data else None

    def update_incident_field(self, incident_id: str, field: str, value: Any):
        state = self.get_incident_state(incident_id) or {}
        state[field] = value
        self.set_incident_state(incident_id, state)

    def store_execution_plan(self, incident_id: str, plan: Dict[str, Any]):
        self._mem[f"plan:{incident_id}"] = plan
        self._safe(lambda: self._client.setex(f"plan:{incident_id}", 7200, json.dumps(plan, default=str)))

    def get_execution_plan(self, incident_id: str) -> Optional[Dict[str, Any]]:
        return self._mem.get(f"plan:{incident_id}") or self._safe(
            lambda: json.loads(self._client.get(f"plan:{incident_id}") or "null"))

    def set_task_status(self, incident_id: str, task_id: str, status: str, result: Any = None):
        key = f"tasks:{incident_id}"
        self._mem.setdefault(key, {})[task_id] = {"status": status, "result": result}
        self._safe(lambda: (self._client.hset(key, task_id, json.dumps({"status": status, "result": result}, default=str)),
                            self._client.expire(key, 7200)))

    def get_all_tasks(self, incident_id: str) -> Dict[str, Any]:
        return self._mem.get(f"tasks:{incident_id}", {})

    def add_active_incident(self, incident_id: str):
        self._mem.setdefault("_active", set()).add(incident_id)
        self._safe(lambda: self._client.sadd("active_incidents", incident_id))

    def remove_active_incident(self, incident_id: str):
        self._mem.get("_active", set()).discard(incident_id)
        self._safe(lambda: self._client.srem("active_incidents", incident_id))

    def get_active_incidents(self) -> List[str]:
        return list(self._mem.get("_active", set()))

    def publish_event(self, channel: str, data: Dict[str, Any]):
        self._safe(lambda: self._client.publish(channel, json.dumps(data, default=str)))

    def publish_incident_update(self, incident_id: str, event_type: str, data: Dict[str, Any]):
        self.publish_event("autosre:incidents", {"incident_id": incident_id, "event_type": event_type, "data": data})

    def ping(self) -> bool:
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass


_redis_client: Optional[RedisClient] = None

def get_redis() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
