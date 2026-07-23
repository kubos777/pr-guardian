"""LLM Client — Unified interface for multiple LLM providers via LiteLLM.

Uses Groq (Llama 3.3 70B) as primary provider for speed and cost ($0),
with Google Gemini 2.0 Flash as automatic fallback if Groq hits rate limits.

Why this stack:
- Groq: 800+ tokens/sec on Llama 3.3 70B, free tier (30 RPM), JSON mode support
- Gemini: 15 RPM free, 1500 req/day, solid structured output
- LiteLLM: Abstracts provider differences behind one interface (OpenAI-compatible)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import litellm
from pydantic import BaseModel

from exceptions import LLMFatalError, LLMTransientError

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True

# Provider configuration
PRIMARY_MODEL = os.environ.get("LLM_MODEL", "groq/llama-3.3-70b-versatile")
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "gemini/gemini-2.0-flash")
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

# LiteLLM reads these env vars automatically:
# GROQ_API_KEY     → for groq/* models
# GEMINI_API_KEY   → for gemini/* models


def _is_transient(error: Exception) -> bool:
    """Classify if an LLM error is retryable (transient) or fatal."""
    error_str = str(error).lower()
    transient_signals = ["rate_limit", "429", "timeout", "503", "overloaded", "capacity"]
    return any(signal in error_str for signal in transient_signals)


def call_llm(
    system_prompt: str,
    user_content: str,
    temperature: float | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Call the LLM with automatic fallback.

    1. Tries PRIMARY_MODEL (Groq/Llama)
    2. On rate limit or transient error, falls back to FALLBACK_MODEL (Gemini)
    3. Classifies errors as transient (retryable) or fatal (not retryable)

    Returns raw text content from the LLM response.
    """
    temp = temperature if temperature is not None else TEMPERATURE
    models = [PRIMARY_MODEL, FALLBACK_MODEL]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    kwargs: dict[str, Any] = {
        "messages": messages,
        "temperature": temp,
        "max_tokens": MAX_TOKENS,
    }

    if response_format:
        kwargs["response_format"] = response_format

    last_error: Exception | None = None

    for model in models:
        try:
            logger.info(f"Calling LLM: {model}")
            response = litellm.completion(model=model, **kwargs)
            content = response.choices[0].message.content

            if not content:
                raise LLMTransientError(f"Empty response from {model}")

            logger.info(f"LLM response received from {model} ({len(content)} chars)")
            return content

        except Exception as e:
            last_error = e
            error_msg = str(e)
            logger.warning(f"LLM call failed on {model}: {error_msg}")

            if _is_transient(e):
                # Try next model
                logger.info(f"Transient error on {model}, trying fallback...")
                continue
            else:
                # Fatal error — don't try fallback
                raise LLMFatalError(f"Fatal LLM error on {model}: {error_msg}") from e

    # All models failed with transient errors
    raise LLMTransientError(
        f"All LLM providers failed. Last error: {last_error}"
    )


def call_llm_json(
    system_prompt: str,
    user_content: str,
    temperature: float | None = None,
) -> dict:
    """Call LLM expecting a JSON response. Parses and returns dict.

    Forces JSON mode on providers that support it.
    Falls back to parsing raw text if JSON mode isn't available.
    """
    response_format = {"type": "json_object"}

    raw = call_llm(
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
        response_format=response_format,
    )

    # Strip markdown fences if model wraps JSON in them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines[1:] if not l.strip() == "```"]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMTransientError(
            f"LLM returned invalid JSON: {e}\nRaw response: {raw[:500]}"
        ) from e


def call_llm_structured(
    system_prompt: str,
    user_content: str,
    schema: type[BaseModel],
    temperature: float | None = None,
) -> BaseModel:
    """Call LLM and validate response against a Pydantic schema.

    Returns a validated Pydantic model instance.
    Raises LLMTransientError if response doesn't match schema (retryable).
    """
    data = call_llm_json(
        system_prompt=system_prompt,
        user_content=user_content,
        temperature=temperature,
    )

    try:
        return schema.model_validate(data)
    except Exception as e:
        raise LLMTransientError(
            f"LLM response doesn't match schema {schema.__name__}: {e}"
        ) from e
