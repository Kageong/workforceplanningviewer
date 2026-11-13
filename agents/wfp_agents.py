"""Multi-agent workforce planning stack (coordinator + specialists)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters

from callbacks.cost_tracker import CostTelemetry, make_after_model_cost_tracker
from guardrails.pii_and_injection import before_model_guardrail

BASE_DIR = Path(__file__).resolve().parents[1]
MCP_SERVER = str(BASE_DIR / "mcp_wfp_server.py")
DB_FILE = str(BASE_DIR / "data" / "enterprise.db")

MCP_TOOLS = ["list_tables", "describe_table", "read_query", "read_policy"]


def _mcp_toolset(working_unit_id: str) -> McpToolset:
    env = {**os.environ.copy(), "WFP_WORKING_UNIT_ID": working_unit_id}
    return McpToolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[MCP_SERVER, DB_FILE],
            env=env,
        ),
        tool_filter=MCP_TOOLS,
        errlog=subprocess.DEVNULL,
    )


def build_coordinator(
    working_unit_id: str,
    unit_name: str,
    manager_name: str,
    telemetry: CostTelemetry,
) -> tuple[Agent, McpToolset]:
    unit_ctx = (
        f"Logged-in manager: {manager_name}. Working unit: {unit_name} "
        f"({working_unit_id}). Every read_query MUST pass "
        f'manager_working_unit_id="{working_unit_id}".'
    )

    shared_mcp = _mcp_toolset(working_unit_id)

    shift_specialist = Agent(
        name="shift_specialist",
        model="gemini-2.5-flash",
        description="Retrieves shift schedules for the manager's unit via MCP.",
        instruction=(
            f"{unit_ctx}\n"
            "You fetch shift data only. Use list_tables/describe_table/read_query.\n"
            "Join shifts to employees when needed and filter by working_unit_id.\n"
            "Return compact JSON: "
            '{"section":"shifts","employee_id":null|"id","rows":[],"notes":""}'
        ),
        tools=[shared_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_cost_tracker(telemetry),
    )

    leave_specialist = Agent(
        name="leave_specialist",
        model="gemini-2.5-flash",
        description="Retrieves leave balances and requests for the manager's unit.",
        instruction=(
            f"{unit_ctx}\n"
            "You fetch leave_balances and leave_requests.\n"
            "Return compact JSON: "
            '{"section":"leave","employee_id":null|"id","balances":[],"requests":[],"notes":""}'
        ),
        tools=[shared_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_cost_tracker(telemetry),
    )

    policy_specialist = Agent(
        name="policy_specialist",
        model="gemini-2.5-flash",
        description="Answers policy questions from markdown handbooks.",
        instruction=(
            f"{unit_ctx}\n"
            "Use read_policy for shift_scheduling_rules.md, leave_and_balance.md, "
            "or manager_data_access.md. Cite the policy file name."
        ),
        tools=[shared_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_cost_tracker(telemetry),
    )

    report_compiler = Agent(
        name="report_compiler",
        model="gemini-2.5-flash",
        description="Merges specialist JSON into a manager-ready employee report.",
        instruction=(
            "You compile structured JSON from shift and leave specialists into a "
            "clear markdown report. Do not invent numbers. If data is missing, say so."
        ),
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_cost_tracker(telemetry),
    )

    coordinator = Agent(
        name="wfp_coordinator",
        model="gemini-2.5-flash",
        description="Routes manager workforce questions to shift, leave, or policy specialists.",
        instruction=(
            f"{unit_ctx}\n"
            "Route shift-only questions to shift_specialist.\n"
            "Route leave-only questions to leave_specialist.\n"
            "Route policy questions to policy_specialist.\n"
            "For employee report requests: call shift_specialist AND leave_specialist "
            "(same employee if specified), then pass both JSON payloads to report_compiler.\n"
            "Never query data yourself; always delegate."
        ),
        tools=[
            AgentTool(agent=shift_specialist),
            AgentTool(agent=leave_specialist),
            AgentTool(agent=policy_specialist),
            AgentTool(agent=report_compiler),
        ],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_cost_tracker(telemetry),
    )

    return coordinator, shared_mcp
