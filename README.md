# Workforce Planning Capstone (WFP)

Enterprise **Workforce Shift & Leave Analyst** for unit managers: login, MCP-backed SQLite queries scoped by `working_unit_id`, multi-agent coordinator (shift, leave, policy, report compiler), guardrails, token telemetry, and golden evaluation.

## Capstone pillars

| Pillar | Implementation |
|--------|----------------|
| Multi-agent | `agents/wfp_agents.py` — coordinator + `AgentTool` specialists |
| MCP + data | `mcp_wfp_server.py`, `data/enterprise.db`, `policies/*.md` |
| Guardrails | `guardrails/pii_and_injection.py`, `is_sql_mutation`, read-only SQLite URI |
| Observability | `callbacks/cost_tracker.py`, sidebar metrics in `app.py` |
| Evaluation | `eval/capstone_golden.json`, `eval/run_eval.py` |
| Deployment | `app.py`, `requirements.txt`, Streamlit secrets |

Unit scoping: every `read_query` requires `manager_working_unit_id`, validated against `WFP_WORKING_UNIT_ID` set when spawning the MCP subprocess for the logged-in manager.

## Quick start

```bash
pip install -r requirements.txt
python scripts/bootstrap_db.py
set GOOGLE_API_KEY=your-key
streamlit run app.py
```

Demo logins (username only):

- `mgr_north` — North Plant (`WU_NORTH`)
- `mgr_south` — South Plant (`WU_SOUTH`)

## Streamlit Cloud

1. Push this repo to GitHub.
2. Deploy `app.py` on [share.streamlit.io](https://share.streamlit.io).
3. Add secret: `GOOGLE_API_KEY`.

## Evaluation

```bash
set GOOGLE_API_KEY=your-key
python eval/run_eval.py
```

Outputs `eval/report.txt`.

## Architecture (summary)

ADK `McpToolset` connects over STDIO to `mcp_wfp_server.py`. Specialists discover schema at runtime (`list_tables`, `describe_table`) and query with `read_query`. The coordinator delegates report requests to shift and leave specialists, then the report compiler merges JSON into a manager-facing summary. Input guardrails redact PII and block injection; the MCP layer blocks SQL mutations and enforces working-unit scope.
