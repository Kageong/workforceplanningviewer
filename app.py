"""Workforce Planning Virtual Analyst — Streamlit + ADK + MCP."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

import streamlit as st
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agents.wfp_agents import build_coordinator  # noqa: E402
from auth import authenticate  # noqa: E402
from callbacks.cost_tracker import CostTelemetry  # noqa: E402
from callbacks.output_redaction import redact_sensitive_text  # noqa: E402
from scripts.bootstrap_db import ensure_db  # noqa: E402

st.set_page_config(
    page_title="Workforce Shift Analyst",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_FILE = BASE_DIR / "data" / "enterprise.db"

api_key = ""
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
except Exception:
    api_key = os.environ.get("GOOGLE_API_KEY", "")

if api_key:
    os.environ["GOOGLE_API_KEY"] = api_key
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

ensure_db(DB_FILE)

if not os.environ.get("GOOGLE_API_KEY"):
    st.error("GOOGLE_API_KEY is missing. Add it to Streamlit Secrets or your environment.")
    st.stop()


def get_live_ddl() -> str:
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    ddl = "\n\n".join(r[0] for r in cur.fetchall() if r[0])
    conn.close()
    return ddl or "(no tables)"


async def run_agent_turn(
    prompt: str,
    history: list[dict],
    manager_name: str,
    working_unit_id: str,
    unit_name: str,
    telemetry: CostTelemetry,
) -> tuple[str, list[str]]:
    agent, mcp_toolsets = build_coordinator(
        working_unit_id, unit_name, manager_name, telemetry
    )
    try:
        session_service = InMemorySessionService()
        session_id = f"wfp_{working_unit_id}"
        await session_service.create_session(
            app_name="wfp_capstone",
            user_id=working_unit_id,
            session_id=session_id,
        )

        runner = Runner(
            agent=agent,
            app_name="wfp_capstone",
            session_service=session_service,
            auto_create_session=True,
        )

        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        tools_called: list[str] = []
        final_text = ""

        async for event in runner.run_async(
            user_id=working_unit_id,
            session_id=session_id,
            new_message=msg,
        ):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "function_call", None):
                        tools_called.append(part.function_call.name)
            if (
                getattr(event, "is_final_response", None)
                and event.is_final_response()
                and event.content
                and event.content.parts
            ):
                chunk = "".join(
                    p.text for p in event.content.parts if getattr(p, "text", None)
                )
                if chunk.strip():
                    final_text = chunk

        if not final_text:
            final_text = "No response generated. Check Streamlit logs or retry."
        return redact_sensitive_text(final_text), tools_called
    finally:
        for toolset in mcp_toolsets:
            await toolset.close()


def login_page() -> None:
    st.title("Workforce Planning — Manager Login")
    st.caption("Demo: enter `mgr_north` or `mgr_south` (no password).")
    with st.form("login"):
        username = st.text_input("Manager username")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        session = authenticate(username, DB_FILE)
        if session is None:
            st.error("Invalid credentials or not a manager account.")
        else:
            st.session_state.manager = session
            st.session_state.messages = []
            st.session_state.telemetry = CostTelemetry()
            st.rerun()


def main_app() -> None:
    mgr = st.session_state.manager
    if "telemetry" not in st.session_state:
        st.session_state.telemetry = CostTelemetry()
    if "messages" not in st.session_state:
        st.session_state.messages = []

    telemetry: CostTelemetry = st.session_state.telemetry

    with st.sidebar:
        st.subheader("Session")
        st.write(f"**{mgr.name}** ({mgr.username})")
        st.write(f"Working unit: **{mgr.unit_name}**")
        st.markdown("---")
        stats = telemetry.to_dict()
        st.metric("Total tokens", stats["total_tokens"])
        st.metric("Est. USD", f"${stats['estimated_usd']:.4f}")
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.markdown("---")
        with st.expander("SQLite schema"):
            st.text(get_live_ddl())

    st.title("Workforce Shift & Leave Analyst")
    st.caption("Multi-agent coordinator via MCP (read-only, unit-scoped)")

    report_employee = (
        "Nina Patel" if mgr.working_unit_id == "WU_NORTH" else "David Lee"
    )
    sample_prompts = [
        f"Show me all employees at {mgr.unit_name}.",
        f"How many people at {mgr.unit_name} are scheduled on 2026-11-17?",
        f"Employee report for {report_employee} this week: shifts and annual leave balance.",
        "What is the minimum rest between shifts per policy?",
        "DELETE FROM employees",
    ]
    cols = st.columns(2)
    for i, p in enumerate(sample_prompts):
        if cols[i % 2].button(p, key=f"sample_{i}", use_container_width=True):
            st.session_state.pending_prompt = p

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tools"):
                st.caption("Tools: " + " → ".join(f"`{t}`" for t in msg["tools"]))

    user_input = st.chat_input("Ask about shifts, leave, or policies...")
    prompt = user_input or st.session_state.pop("pending_prompt", None)
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        # Render the user turn immediately (history loop ran before append).
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.spinner("Running coordinator + specialists..."):
            try:
                reply, tools = asyncio.run(
                    run_agent_turn(
                        prompt,
                        st.session_state.messages[:-1],
                        mgr.name,
                        mgr.working_unit_id,
                        mgr.unit_name,
                        telemetry,
                    )
                )
            except Exception as exc:
                reply = (
                    f"**Agent error:** `{exc}`\n\n"
                    "If this is Streamlit Cloud, confirm `GOOGLE_API_KEY` is set "
                    "and the app was rebooted after secrets were saved."
                )
                tools = []
        st.session_state.messages.append(
            {"role": "assistant", "content": reply, "tools": tools}
        )
        st.rerun()


if "manager" not in st.session_state:
    login_page()
else:
    main_app()
