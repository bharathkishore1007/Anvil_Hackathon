"""
AutoSRE — Gemini LLM Provider
Drop-in replacement for Ollama when deploying to cloud.
Uses Google's Gemini API via the new google-genai SDK.
"""

import json
import logging
from typing import Any, Dict, List

from google import genai
from google.genai import types

logger = logging.getLogger("autosre.llm.gemini")


class GeminiProvider:
    """Provides LLM inference via Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        logger.info(f"[Gemini] Initialized with model: {model}")

    def chat(self, messages: List[Dict], temperature: float = 0.3) -> Dict[str, Any]:
        """Call Gemini chat API. Accepts OpenAI-style messages list."""
        try:
            # Convert OpenAI-style messages to single prompt
            system_msg = ""
            user_parts = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    system_msg = content
                else:
                    user_parts.append(content)

            full_prompt = ""
            if system_msg:
                full_prompt = system_msg + "\n\n"
            full_prompt += "\n\n".join(user_parts)

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=2048,
                ),
            )

            content = response.text if response.text else ""
            token_count = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                token_count = getattr(response.usage_metadata, 'total_token_count', 0)

            logger.info(f"[Gemini] Response: {len(content)} chars, {token_count} tokens")
            return {
                "content": content,
                "model": self.model_name,
                "eval_count": token_count,
                "total_duration": 0,
            }

        except Exception as e:
            logger.error(f"[Gemini] API call failed: {e}")
            return {"content": "", "error": str(e)}


# Singleton
_provider = None


def get_gemini(api_key: str = None, model: str = "gemini-2.5-flash") -> GeminiProvider:
    """Get or create Gemini provider singleton."""
    global _provider
    if _provider is None:
        if not api_key:
            from config import settings
            api_key = settings.GEMINI_API_KEY
        _provider = GeminiProvider(api_key, model)
    return _provider
