"""Multi-agent workforce planning stack (coordinator + specialists)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters

from callbacks.cost_tracker import CostTelemetry, make_after_model_pipeline
from guardrails.pii_and_injection import before_model_guardrail

BASE_DIR = Path(__file__).resolve().parents[1]
MCP_SERVER = str(BASE_DIR / "mcp_wfp_server.py")
DB_FILE = str(BASE_DIR / "data" / "enterprise.db")

MCP_TOOLS = ["list_tables", "describe_table", "read_query", "read_policy"]
MODEL_ID = "gemini-3.5-flash"


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
        f"Logged-in manager: {manager_name}. Working unit name: {unit_name}. "
        f'MCP read_query must pass manager_working_unit_id="{working_unit_id}" '
        f"(internal ID — never show this ID to the manager unless they ask).\n"
        "Managers use plain language: employee names (e.g. Nina Patel) and "
        f"unit names (e.g. {unit_name}), not codes like E_N101 or WU_NORTH. "
        "Resolve names with SQL joins on employees.name and working_units.unit_name."
    )

    roster_mcp = _mcp_toolset(working_unit_id)
    shift_mcp = _mcp_toolset(working_unit_id)
    leave_mcp = _mcp_toolset(working_unit_id)
    policy_mcp = _mcp_toolset(working_unit_id)
    mcp_toolsets = [roster_mcp, shift_mcp, leave_mcp, policy_mcp]

    employee_specialist = Agent(
        name="employee_specialist",
        model=MODEL_ID,
        description="Lists employees in the manager's working unit via MCP.",
        instruction=(
            f"{unit_ctx}\n"
            "You answer roster questions: list all employees, count employees, "
            "Lookup by employee name first; use employee_id only internally.\n"
            "Use list_tables, describe_table, read_query (join working_units for unit_name).\n"
            "Return a markdown table with name, role, contact_number, email "
            "(redacted); omit technical IDs unless required."
        ),
        tools=[roster_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    shift_specialist = Agent(
        name="shift_specialist",
        model=MODEL_ID,
        description="Retrieves shift schedules for the manager's unit via MCP.",
        instruction=(
            f"{unit_ctx}\n"
            "You fetch shift data only. Use list_tables/describe_table/read_query.\n"
            "Join shifts to employees for employee names; filter by unit.\n"
            "Return compact JSON: "
            '{"section":"shifts","employee_name":null|"name","rows":[],"notes":""}'
        ),
        tools=[shift_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    leave_specialist = Agent(
        name="leave_specialist",
        model=MODEL_ID,
        description="Retrieves leave balances and requests for the manager's unit.",
        instruction=(
            f"{unit_ctx}\n"
            "You fetch leave_balances and leave_requests.\n"
            "Return compact JSON: "
            '{"section":"leave","employee_name":null|"name","balances":[],"requests":[],"notes":""}'
        ),
        tools=[leave_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    policy_specialist = Agent(
        name="policy_specialist",
        model=MODEL_ID,
        description="Answers policy questions from markdown handbooks.",
        instruction=(
            f"{unit_ctx}\n"
            "Use read_policy for shift_scheduling_rules.md, leave_and_balance.md, "
            "or manager_data_access.md. Cite the policy file name."
        ),
        tools=[policy_mcp],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    report_compiler = Agent(
        name="report_compiler",
        model=MODEL_ID,
        description="Merges specialist JSON into a manager-ready employee report.",
        instruction=(
            "You compile structured JSON from shift and leave specialists into a "
            "clear markdown report using employee names and the working unit name. "
            "Do not invent numbers. If data is missing, say so."
        ),
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    coordinator = Agent(
        name="wfp_coordinator",
        model=MODEL_ID,
        description="Routes manager workforce questions to shift, leave, or policy specialists.",
        instruction=(
            f"{unit_ctx}\n"
            "Route roster questions (list/show/count employees in my unit) to employee_specialist.\n"
            "Route shift-only questions to shift_specialist.\n"
            "Route leave-only questions to leave_specialist.\n"
            "Route policy questions to policy_specialist.\n"
            "For employee report requests: call shift_specialist AND leave_specialist "
            "(same employee if specified), then pass both JSON payloads to report_compiler.\n"
            "Never query data yourself; always delegate."
        ),
        tools=[
            AgentTool(agent=employee_specialist),
            AgentTool(agent=shift_specialist),
            AgentTool(agent=leave_specialist),
            AgentTool(agent=policy_specialist),
            AgentTool(agent=report_compiler),
        ],
        before_model_callback=before_model_guardrail,
        after_model_callback=make_after_model_pipeline(telemetry),
    )

    return coordinator, mcp_toolsets
