"""After-model guardrail: mask email and phone in model text (show last 5 chars)."""

from __future__ import annotations

import re

from google.adk.models import LlmResponse
from google.genai import types

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
# Phone: optional +, digits/separators, at least 8 digit chars total
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s\-().]{6,}\d)(?!\w)",
)


def mask_keep_last(value: str, visible: int = 5) -> str:
    value = value.strip()
    if len(value) <= visible:
        return value
    return ("*" * (len(value) - visible)) + value[-visible:]


def redact_sensitive_text(text: str) -> str:
    def _email(match: re.Match[str]) -> str:
        return mask_keep_last(match.group(0), 5)

    def _phone(match: re.Match[str]) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 8:
            return raw
        return mask_keep_last(raw, 5)

    text = EMAIL_RE.sub(_email, text)
    text = PHONE_RE.sub(_phone, text)
    return text


def after_model_output_redaction(callback_context, llm_response: LlmResponse):
    """Redact PII in model-visible text; keep only last 5 characters."""
    if llm_response.partial:
        return None
    if not llm_response.content or not llm_response.content.parts:
        return None

    changed = False
    new_parts: list[types.Part] = []
    for part in llm_response.content.parts:
        if getattr(part, "text", None):
            redacted = redact_sensitive_text(part.text)
            if redacted != part.text:
                changed = True
            new_parts.append(types.Part(text=redacted))
        else:
            new_parts.append(part)

    if not changed:
        return None

    return LlmResponse(
        content=types.Content(role=llm_response.content.role, parts=new_parts),
        usage_metadata=llm_response.usage_metadata,
        partial=llm_response.partial,
    )
