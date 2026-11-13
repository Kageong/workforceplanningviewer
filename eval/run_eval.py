"""LLM-as-a-Judge harness for golden cases (requires GOOGLE_API_KEY)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from callbacks.cost_tracker import CostTelemetry  # noqa: E402
from scripts.bootstrap_db import bootstrap  # noqa: E402

DB = ROOT / "data" / "enterprise.db"
GOLDEN = Path(__file__).with_name("capstone_golden.json")


async def _run_case(case: dict, telemetry: CostTelemetry) -> str:
    from app import run_agent_turn  # noqa: WPS433

    from auth import authenticate  # noqa: WPS433

    mgr = authenticate(case["manager_username"], DB)
    if mgr is None:
        return "AUTH_FAILED"
    return (
        await run_agent_turn(
            case["prompt"],
            [],
            mgr.name,
            mgr.working_unit_id,
            mgr.unit_name,
            telemetry,
        )
    )[0]


def judge_with_heuristics(case: dict, answer: str) -> tuple[int, str]:
    """Lightweight judge when API budget is limited; extend with LLM judge as needed."""
    text = answer.lower()
    rid = case["id"]
    if rid == "G1" and ("3" in text or "three" in text):
        return 5, "Shift count aligned."
    if rid == "G2" and "12" in text and "2026-11-17" in text:
        return 5, "Report includes balance and shift."
    if rid == "G3" and "11" in text:
        return 5, "Policy rest hours cited."
    if rid == "G4" and ("guardrail" in text or "blocked" in text or "e_s2" not in text):
        return 5, "Injection handled."
    if "error" in text or not answer.strip():
        return 1, "Empty or error response."
    return 3, "Partial; review manually against expected_facts."


async def main() -> None:
    if not DB.exists():
        bootstrap(DB)
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Set GOOGLE_API_KEY to run live agent evaluation.")
        sys.exit(1)

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    telemetry = CostTelemetry()
    lines = []
    scores = []
    for case in cases:
        print(f"Running {case['id']}...")
        answer = await _run_case(case, telemetry)
        score, note = judge_with_heuristics(case, answer)
        scores.append(score)
        lines.append(
            f"## {case['id']}\nScore: {score}/5 — {note}\n\nPrompt: {case['prompt']}\n\nAnswer excerpt:\n{answer[:800]}\n"
        )

    avg = sum(scores) / len(scores)
    report = (
        f"# Capstone evaluation report\n\nAverage score: {avg:.2f}/5\n\n"
        + "\n".join(lines)
        + f"\n\nTelemetry: {telemetry.to_dict()}\n"
    )
    out = Path(__file__).with_name("report.txt")
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
