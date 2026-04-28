"""LLM helpers for AutoSkill (OpenAI-compatible API)."""

from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LLM_MODEL", "gemma-4-26b-a4b-it-4bit")
LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:1111/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "test")


def strip_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


# Keep old names as aliases for backward compatibility
_strip_fences = strip_fences


def clean_json(text: str) -> str:
    """Strip markdown fences and fix trailing-comma issues in LLM JSON output."""
    cleaned = strip_fences(text)
    cleaned = re.sub(r",\s*}", "}", cleaned)
    cleaned = re.sub(r",\s*]", "]", cleaned)
    return cleaned


async def llm_call(prompt: str) -> str:
    """Make a raw LLM call and return the response content string."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            LLM_URL,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


# Keep old name as alias for backward compatibility
_llm_call = llm_call
