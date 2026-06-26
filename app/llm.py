"""
OPTIONAL, FALLBACK-ONLY LLM layer. Disabled unless USE_LLM=1 and a key is present.

Scope is deliberately tiny: for a LOW-confidence ticket the rules classified as
`other`, the LLM may *suggest a more specific case_type*. That suggestion is validated
against our enums and only used to PROMOTE `other` (see rules.decide). The LLM never
writes the customer_reply, never sets severity/escalation, and never relaxes safety —
those stay 100% rule-driven. On any failure (no key, timeout, bad JSON, off-enum) we
keep the deterministic rule result.

Provider is OpenAI-compatible: Groq (primary), Cerebras or Gemini by swapping
LLM_BASE_URL + LLM_MODEL only.
"""
from __future__ import annotations

import json
import os

from .schemas import CaseType

USE_LLM = os.getenv("USE_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", os.getenv("LLM_TIMEOUT_SECONDS", "3.5")))

_VALID = {e.value for e in CaseType}

_SYSTEM = (
    "You classify a digital-finance support complaint into exactly one case_type. "
    f"Return ONLY JSON: {{\"case_type\": one of {sorted(_VALID)}}}. "
    "Pick the single best fit. No prose, no markdown."
)


def maybe_available() -> bool:
    return USE_LLM and bool(LLM_API_KEY)


def suggest_case_type(complaint: str) -> CaseType | None:
    """Return a validated CaseType suggestion, or None on any problem."""
    if not maybe_available():
        return None
    try:
        import httpx

        resp = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "temperature": 0,
                "max_tokens": 40,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": (complaint or "")[:2000]},
                ],
            },
            timeout=LLM_TIMEOUT_S,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        ct = json.loads(content).get("case_type")
        if ct in _VALID:
            return CaseType(ct)
        return None
    except Exception:
        return None
