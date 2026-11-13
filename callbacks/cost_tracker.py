"""Post-model token and cost telemetry."""

from __future__ import annotations

from google.adk.models import LlmResponse

# Gemini 2.5 Flash approximate USD per 1M tokens (course-style estimate).
PROMPT_USD_PER_M = 0.075
OUTPUT_USD_PER_M = 0.30


class CostTelemetry:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.estimated_usd = 0.0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_usd": round(self.estimated_usd, 6),
        }


def make_after_model_cost_tracker(telemetry: CostTelemetry):
    def after_model_cost_tracker(callback_context, llm_response: LlmResponse):
        meta = llm_response.usage_metadata
        if not meta:
            return None
        prompt = meta.prompt_token_count or 0
        completion = meta.candidates_token_count or 0
        total = meta.total_token_count or (prompt + completion)
        telemetry.prompt_tokens += prompt
        telemetry.completion_tokens += completion
        telemetry.total_tokens += total
        telemetry.estimated_usd += (prompt / 1_000_000) * PROMPT_USD_PER_M
        telemetry.estimated_usd += (completion / 1_000_000) * OUTPUT_USD_PER_M
        return None

    return after_model_cost_tracker
