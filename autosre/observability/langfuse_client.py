"""
AutoSRE — Langfuse Observability Client (v4 API)
Uses start_as_current_observation for OpenTelemetry-compatible tracing.
"""

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger("autosre.observability")

_langfuse = None
_langfuse_available = False


def _init_langfuse():
    """Lazy, non-blocking Langfuse init."""
    global _langfuse, _langfuse_available
    if _langfuse is not None:
        return
    try:
        from config import settings
        if not settings.has_langfuse():
            logger.info("Langfuse not configured (no keys)")
            _langfuse = False  # Mark as attempted
            return
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_BASE_URL,
        )
        if _langfuse.auth_check():
            _langfuse_available = True
            logger.info("✅ Langfuse initialized and authenticated")
        else:
            logger.warning("Langfuse auth check failed")
            _langfuse_available = False
    except Exception as e:
        logger.info(f"Langfuse unavailable: {e}")
        _langfuse = False


class TraceContext:
    """Wraps a Langfuse observation/trace for an agent run."""

    def __init__(self, name: str, incident_id: str = "", metadata: Dict = None):
        self.name = name
        self.trace_id = str(uuid.uuid4())
        self.incident_id = incident_id
        self._start_time = time.time()
        self._obs = None

        _init_langfuse()
        if _langfuse_available and _langfuse:
            try:
                self._obs = _langfuse.start_as_current_observation(
                    name=name,
                    input={"incident_id": incident_id, **(metadata or {})},
                )
            except Exception as e:
                logger.debug(f"Langfuse trace create failed: {e}")

        logger.info(f"[TRACE] {name} | incident={incident_id}")

    def span(self, name: str, input_data: Any = None) -> "SpanContext":
        return SpanContext(self, name, input_data)

    def generation(self, name: str, model: str, input_data: Any = None,
                   output_data: Any = None, usage: Dict = None):
        """Log an LLM generation/call."""
        if _langfuse_available and _langfuse:
            try:
                _langfuse.update_current_span(
                    name=name,
                    output=str(output_data)[:500] if output_data else None,
                    metadata={
                        "model": model,
                        "tokens": usage.get("total_tokens", 0) if usage else 0,
                    },
                )
            except Exception as e:
                logger.debug(f"Langfuse generation log failed: {e}")

        tokens = usage.get("total_tokens", "?") if usage else "?"
        logger.info(f"[GEN] {name} | model={model} | tokens={tokens}")

    def end(self, output: Any = None, status: str = "completed"):
        dur = int((time.time() - self._start_time) * 1000)
        if self._obs:
            try:
                self._obs.__exit__(None, None, None)
            except Exception:
                pass
        logger.info(f"[TRACE END] {self.name} | {status} | {dur}ms")

    def score(self, name: str, value: float, comment: str = ""):
        if _langfuse_available and _langfuse:
            try:
                _langfuse.score_current_trace(name=name, value=value, comment=comment)
            except Exception:
                pass


class SpanContext:
    def __init__(self, trace: TraceContext, name: str, input_data: Any = None):
        self.name = name
        self._start = time.time()

    def end(self, output: Any = None, status: str = "completed"):
        dur = int((time.time() - self._start) * 1000)
        return dur


@contextmanager
def trace_agent(agent_name: str, incident_id: str = "", metadata: Dict = None):
    """Context manager for tracing an entire agent run."""
    _init_langfuse()
    
    if _langfuse_available and _langfuse:
        try:
            with _langfuse.start_as_current_observation(
                name=f"agent:{agent_name}",
                input={"incident_id": incident_id, "agent": agent_name, **(metadata or {})},
            ):
                ctx = TraceContext(f"agent:{agent_name}", incident_id, metadata)
                try:
                    yield ctx
                except Exception as e:
                    _langfuse.update_current_span(output=f"Error: {e}", metadata={"status": "error"})
                    raise
                else:
                    _langfuse.update_current_span(
                        output="completed",
                        metadata={"status": "completed", "duration_ms": int((time.time() - ctx._start_time) * 1000)},
                    )
        except Exception as outer_e:
            # If Langfuse context manager fails, still run the agent without tracing
            ctx = TraceContext(f"agent:{agent_name}", incident_id, metadata)
            try:
                yield ctx
            except Exception:
                raise
    else:
        # No Langfuse — just provide context without tracing
        ctx = TraceContext(f"agent:{agent_name}", incident_id, metadata)
        try:
            yield ctx
        except Exception as e:
            ctx.end(str(e), "error")
            raise
        else:
            ctx.end(status="completed")


@contextmanager
def trace_tool(trace_ctx: TraceContext, tool_name: str, input_data: Any = None):
    span = trace_ctx.span(f"tool:{tool_name}", input_data)
    try:
        yield span
    except Exception as e:
        span.end(str(e), "error")
        raise
    else:
        span.end(status="completed")


def flush():
    """Flush all pending Langfuse events."""
    _init_langfuse()
    if _langfuse_available and _langfuse:
        try:
            _langfuse.flush()
            logger.info("[Langfuse] Traces flushed")
        except Exception as e:
            logger.warning(f"[Langfuse] Flush failed: {e}")
