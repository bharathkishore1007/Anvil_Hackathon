"""
AutoSRE — Langfuse Observability Client
Tracing with console fallback. Non-blocking initialization.
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
    if _langfuse_available:
        return
    try:
        from config import settings
        if not settings.has_langfuse():
            return
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_BASE_URL,
        )
        _langfuse_available = True
        logger.info("Langfuse initialized")
    except Exception as e:
        logger.info(f"Langfuse unavailable: {e}")


class TraceContext:
    def __init__(self, name: str, incident_id: str = "", metadata: Dict = None):
        self.name = name
        self.trace_id = str(uuid.uuid4())
        self.incident_id = incident_id
        self._trace = None
        self._start_time = time.time()

        _init_langfuse()
        if _langfuse_available and _langfuse:
            try:
                self._trace = _langfuse.trace(
                    name=name, id=self.trace_id,
                    metadata={"incident_id": incident_id, **(metadata or {})},
                    tags=["autosre", name],
                )
            except Exception:
                pass
        logger.info(f"[TRACE] {name} | incident={incident_id}")

    def span(self, name: str, input_data: Any = None) -> "SpanContext":
        return SpanContext(self, name, input_data)

    def generation(self, name: str, model: str, input_data: Any = None,
                   output_data: Any = None, usage: Dict = None):
        if self._trace:
            try:
                self._trace.generation(name=name, model=model, input=input_data,
                                       output=output_data, usage=usage or {})
            except Exception:
                pass
        logger.info(f"[GEN] {name} | model={model} | tokens={usage.get('total_tokens', '?') if usage else '?'}")

    def end(self, output: Any = None, status: str = "completed"):
        dur = int((time.time() - self._start_time) * 1000)
        if self._trace:
            try:
                self._trace.update(output=output, metadata={"status": status, "duration_ms": dur})
            except Exception:
                pass
        logger.info(f"[TRACE END] {self.name} | {status} | {dur}ms")

    def score(self, name: str, value: float, comment: str = ""):
        if self._trace:
            try:
                self._trace.score(name=name, value=value, comment=comment)
            except Exception:
                pass


class SpanContext:
    def __init__(self, trace: TraceContext, name: str, input_data: Any = None):
        self.name = name
        self._span = None
        self._start = time.time()
        if trace._trace:
            try:
                self._span = trace._trace.span(name=name, input=input_data)
            except Exception:
                pass

    def end(self, output: Any = None, status: str = "completed"):
        dur = int((time.time() - self._start) * 1000)
        if self._span:
            try:
                self._span.end(output=output, metadata={"status": status})
            except Exception:
                pass
        return dur


@contextmanager
def trace_agent(agent_name: str, incident_id: str = "", metadata: Dict = None):
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
    if _langfuse_available and _langfuse:
        try:
            _langfuse.flush()
        except Exception:
            pass
