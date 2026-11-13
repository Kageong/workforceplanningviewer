"""Input-tier guardrails for WFP agents."""

from __future__ import annotations

import re

from google.adk.models import LlmResponse
from google.genai import types

INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"show\s+all\s+working\s+units",
    r"show\s+employees?\s+from\s+(other|another|all)\s+units?",
    r"other\s+working\s+unit",
    r"drop\s+table",
    r"delete\s+from",
    r"system\s+prompt",
)

DESTRUCTIVE_KEYWORDS = (
    "delete",
    "drop table",
    "truncate",
    "wipe database",
    "update employees",
    "insert into",
)


def redact_pii(text: str) -> str:
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "[REDACTED_EMAIL]",
        text,
    )
    text = re.sub(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[REDACTED_PHONE]", text)
    text = re.sub(r"\b\d{12,16}\b", "[REDACTED_ID]", text)
    return text


def before_model_guardrail(callback_context, llm_request):
    if not llm_request.contents:
        return None
    parts = llm_request.contents[-1].parts or []
    if not parts or not parts[0].text:
        return None

    raw = parts[0].text
    lowered = raw.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=(
                                "[GUARDRAIL] Request blocked: potential prompt "
                                "injection or policy bypass. Operations are "
                                "read-only and scoped to your working unit only."
                            )
                        )
                    ],
                )
            )

    if any(k in lowered for k in DESTRUCTIVE_KEYWORDS):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=(
                            "[GUARDRAIL] Request blocked: destructive or "
                            "data-mutation instructions are not allowed."
                        )
                    )
                ],
            )
        )

    redacted = redact_pii(raw)
    if redacted != raw:
        llm_request.contents[-1].parts[0].text = redacted
    return None
