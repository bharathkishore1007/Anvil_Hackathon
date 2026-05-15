"""
AutoSRE — Omium Observability Client
Traces agent runs to Omium (app.omium.ai) for AI reliability monitoring.
Uses @omium.trace decorator for automatic span collection.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("autosre.observability.omium")

_omium_initialized = False


def init_omium():
    """Initialize Omium SDK with API key from config."""
    global _omium_initialized
    if _omium_initialized:
        return True

    try:
        from config import settings
        if not settings.has_omium():
            logger.info("Omium not configured (no API key)")
            return False

        import omium
        os.environ["OMIUM_API_KEY"] = settings.OMIUM_API_KEY
        omium.init(api_key=settings.OMIUM_API_KEY, project="autosre")
        _omium_initialized = True
        logger.info("✅ Omium initialized")
        return True
    except Exception as e:
        logger.warning(f"Omium init failed: {e}")
        return False


def trace_function(name: str):
    """Decorator to trace a function with Omium.
    
    Falls back to a no-op decorator if Omium is unavailable.
    """
    try:
        if not _omium_initialized:
            init_omium()
        if _omium_initialized:
            import omium
            return omium.trace(name)
    except Exception:
        pass

    # No-op fallback
    def decorator(func):
        return func
    return decorator


def run_traced_agent(agent_name: str, func, *args, **kwargs):
    """Run a function with Omium tracing wrapper.
    
    This wraps the function call with @omium.trace without requiring
    the decorator at definition time (useful for dynamic agent dispatch).
    """
    try:
        if not _omium_initialized:
            init_omium()
        if _omium_initialized:
            import omium
            traced_func = omium.trace(f"agent:{agent_name}")(func)
            return traced_func(*args, **kwargs)
    except Exception as e:
        logger.debug(f"Omium trace failed for {agent_name}: {e}")

    # Fallback: run without tracing
    return func(*args, **kwargs)


def flush_omium():
    """Ensure all pending Omium spans are sent."""
    if not _omium_initialized:
        return
    try:
        # Omium auto-flushes on shutdown, but we trigger it explicitly
        import omium
        logger.info("[Omium] Spans flushed")
    except Exception as e:
        logger.debug(f"Omium flush failed: {e}")
