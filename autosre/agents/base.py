"""
AutoSRE — Base Agent
Foundation for all AI agents. Uses Ollama (OpenAI-compatible API) for LLM reasoning.
Handles the tool-use loop, structured output parsing, retries, and observability.
"""

import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import httpx

from config import settings
from observability.langfuse_client import TraceContext, trace_agent
from memory.postgres_client import get_postgres

logger = logging.getLogger("autosre.agents.base")


class BaseAgent:
    """Base class for all AutoSRE agents.
    
    Each agent has:
    - A name and system prompt defining its role
    - A set of tools it can invoke
    - Integration with Ollama for LLM reasoning
    - Langfuse observability tracing
    """

    def __init__(self, name: str, system_prompt: str, tools: Dict[str, Callable] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.model = settings.OLLAMA_MODEL
        self.fallback_model = settings.OLLAMA_FALLBACK_MODEL
        self.base_url = settings.OLLAMA_BASE_URL
        self._use_gemini = settings.has_gemini()
        if self._use_gemini:
            from llm.gemini_provider import get_gemini
            self._gemini = get_gemini(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
            self.model = settings.GEMINI_MODEL
            logger.info(f"[{name}] Using Gemini API: {self.model}")

    def _build_tool_descriptions(self) -> str:
        """Build a text description of available tools for the system prompt."""
        if not self.tools:
            return ""
        lines = ["\n\nAvailable tools:"]
        for name, func in self.tools.items():
            doc = func.__doc__ or "No description"
            lines.append(f"- {name}: {doc.strip().split(chr(10))[0]}")
        return "\n".join(lines)

    def _call_ollama(self, messages: List[Dict], model: str = None) -> Dict[str, Any]:
        """Call LLM — uses Gemini if configured, otherwise Ollama."""

        # Use Gemini if available
        if self._use_gemini:
            return self._gemini.chat(messages)

        # Otherwise use Ollama
        model = model or self.model
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            },
        }

        try:
            response = httpx.post(url, json=payload, timeout=120.0)
            if response.status_code == 200:
                data = response.json()
                return {
                    "content": data.get("message", {}).get("content", ""),
                    "model": model,
                    "total_duration": data.get("total_duration", 0),
                    "eval_count": data.get("eval_count", 0),
                }
            else:
                logger.error(f"Ollama returned {response.status_code}: {response.text[:200]}")
                return {"content": "", "error": f"HTTP {response.status_code}"}
        except httpx.TimeoutException:
            logger.warning(f"Ollama timeout with {model}, trying fallback...")
            if model != self.fallback_model:
                return self._call_ollama(messages, self.fallback_model)
            return {"content": "", "error": "Timeout"}
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return {"content": "", "error": str(e)}

    def run(self, input_data: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
        """Execute the agent's reasoning loop.
        
        1. Build prompt with system context + input
        2. Call Ollama for reasoning
        3. Parse structured output
        4. Execute any tool calls
        5. Return aggregated result
        """
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        # Log agent run start
        pg = get_postgres()
        pg.create_agent_run({
            "run_id": run_id,
            "incident_id": incident_id,
            "agent_type": self.name,
            "task_input": input_data,
        })

        with trace_agent(self.name, incident_id) as trace:
            try:
                # Build messages
                system_msg = self.system_prompt + self._build_tool_descriptions()
                system_msg += (
                    "\n\nIMPORTANT: Always respond with valid JSON. Your response must be a JSON object "
                    "with at minimum a 'result' key containing your findings/output."
                )

                messages = [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": json.dumps(input_data, default=str)},
                ]

                # Call LLM
                response = self._call_ollama(messages)
                raw_content = response.get("content", "")

                # Log generation
                trace.generation(
                    name=f"{self.name}_reasoning",
                    model=response.get("model", self.model),
                    input_data=input_data,
                    output_data=raw_content[:500],
                    usage={"total_tokens": response.get("eval_count", 0)},
                )

                # Parse response
                result = self._parse_response(raw_content, input_data)
                result["_meta"] = {
                    "agent": self.name,
                    "run_id": run_id,
                    "model": response.get("model", self.model),
                    "duration_ms": int((time.time() - start_time) * 1000),
                    "tokens": response.get("eval_count", 0),
                }

                # Complete agent run
                duration_ms = int((time.time() - start_time) * 1000)
                pg.complete_agent_run(
                    run_id, result, "completed", duration_ms,
                    response.get("eval_count", 0)
                )

                return result

            except Exception as e:
                logger.error(f"Agent {self.name} failed: {e}")
                duration_ms = int((time.time() - start_time) * 1000)
                pg.complete_agent_run(run_id, None, "failed", duration_ms, error=str(e))
                return {
                    "error": str(e),
                    "agent": self.name,
                    "_meta": {"agent": self.name, "run_id": run_id, "status": "failed"},
                }

    def _parse_response(self, content: str, input_data: Dict) -> Dict[str, Any]:
        """Parse LLM response — try JSON first, fall back to structured extraction."""
        # Try to find JSON in the response
        content = content.strip()

        # Try direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find any JSON object in the text
        brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: wrap raw text in a result object
        return {"result": content, "raw": True}

    def _execute_tool(self, tool_name: str, args: Dict, trace: TraceContext,
                      run_id: str) -> Any:
        """Execute a tool and log the call."""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}

        call_id = f"call-{uuid.uuid4().hex[:8]}"
        start = time.time()

        span = trace.span(f"tool:{tool_name}", args)
        try:
            result = self.tools[tool_name](**args)
            duration = int((time.time() - start) * 1000)
            span.end(result, "completed")

            # Log tool call
            pg = get_postgres()
            pg.log_tool_call({
                "call_id": call_id,
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": args,
                "tool_output": result,
                "status": "completed",
                "duration_ms": duration,
            })

            return result
        except Exception as e:
            span.end(str(e), "error")
            return {"error": str(e)}
