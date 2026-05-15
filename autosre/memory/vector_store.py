"""
AutoSRE — Vector Store
pgvector-based similarity search for finding similar past incidents.
Uses Ollama embeddings and psycopg3.
"""

import hashlib
import logging
import struct
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger("autosre.memory.vector_store")

EMBEDDING_DIM = 384


def _generate_embedding_ollama(text: str) -> List[float]:
    """Generate an embedding using Ollama's API, fallback to hash."""
    try:
        response = httpx.post(
            f"{settings.OLLAMA_BASE_URL}/api/embeddings",
            json={"model": settings.OLLAMA_MODEL, "prompt": text},
            timeout=30.0,
        )
        if response.status_code == 200:
            embedding = response.json().get("embedding", [])
            if embedding:
                if len(embedding) < EMBEDDING_DIM:
                    embedding.extend([0.0] * (EMBEDDING_DIM - len(embedding)))
                return embedding[:EMBEDDING_DIM]
    except Exception as e:
        logger.warning(f"Ollama embedding failed: {e}")
    return _hash_embedding(text)


def _hash_embedding(text: str) -> List[float]:
    """Deterministic pseudo-embedding from text hashing."""
    result = []
    for i in range(EMBEDDING_DIM):
        h = hashlib.sha256(f"{text}:{i}".encode()).digest()
        val = struct.unpack('f', h[:4])[0]
        val = max(-1.0, min(1.0, val / 1e30))
        result.append(val)
    return result


class VectorStore:
    """pgvector-backed similarity search for incident history."""

    def __init__(self):
        self._conn = None
        self._last_fail = 0

    def _get_conn(self):
        if self._conn is not None:
            try:
                if not self._conn.closed:
                    return self._conn
            except Exception:
                pass
            self._conn = None

        import time
        if time.time() - self._last_fail < 30:
            return None

        try:
            import psycopg
            conninfo = (
                f"host={settings.POSTGRES_HOST} port={settings.POSTGRES_PORT} "
                f"dbname={settings.POSTGRES_DB} user={settings.POSTGRES_USER} "
                f"password={settings.POSTGRES_PASSWORD} connect_timeout=1"
            )
            self._conn = psycopg.connect(conninfo, autocommit=True)
            return self._conn
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable for vector store: {e}")
            self._conn = None
            self._last_fail = time.time()
            return None

    def store_incident_embedding(self, incident_id: str, text: str) -> bool:
        conn = self._get_conn()
        if not conn:
            return False
        embedding = _generate_embedding_ollama(text)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE incidents SET embedding = %s::vector WHERE incident_id = %s",
                    (str(embedding), incident_id),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            return False

    def find_similar_incidents(self, text: str, limit: int = 5,
                               exclude_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if not conn:
            return self._fallback_similar(text, limit)

        embedding = _generate_embedding_ollama(text)
        try:
            with conn.cursor() as cur:
                if exclude_id:
                    cur.execute(
                        """SELECT incident_id, title, description, root_cause, resolution,
                                  severity, status, created_at,
                                  1 - (embedding <=> %s::vector) AS similarity
                           FROM incidents
                           WHERE embedding IS NOT NULL AND incident_id != %s
                           ORDER BY embedding <=> %s::vector LIMIT %s""",
                        (str(embedding), exclude_id, str(embedding), limit),
                    )
                else:
                    cur.execute(
                        """SELECT incident_id, title, description, root_cause, resolution,
                                  severity, status, created_at,
                                  1 - (embedding <=> %s::vector) AS similarity
                           FROM incidents WHERE embedding IS NOT NULL
                           ORDER BY embedding <=> %s::vector LIMIT %s""",
                        (str(embedding), str(embedding), limit),
                    )
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return self._fallback_similar(text, limit)

    def _fallback_similar(self, text: str, limit: int) -> List[Dict[str, Any]]:
        """Keyword-based fallback."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            keywords = text.lower().split()[:5]
            conditions = " OR ".join(["LOWER(title) LIKE %s" for _ in keywords])
            params = [f"%{kw}%" for kw in keywords]
            params.append(limit)
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT incident_id, title, description, root_cause, resolution,
                               severity, status, created_at
                        FROM incidents WHERE status = 'resolved' AND ({conditions})
                        ORDER BY created_at DESC LIMIT %s""",
                    params,
                )
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []


_vector_store: Optional[VectorStore] = None

def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
