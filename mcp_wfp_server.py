"""MCP SQLite server for workforce planning (read-only, unit-scoped)."""

import json
import os
import sqlite3
import sys
from pathlib import Path

import sqlparse

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

mcp = MCPServer("WorkforcePlanningMCPServer")

DB_FILE = sys.argv[1] if len(sys.argv) > 1 else str(
    Path(__file__).resolve().parent / "data" / "enterprise.db"
)
POLICIES_DIR = Path(__file__).resolve().parent / "policies"
SESSION_UNIT = os.environ.get("WFP_WORKING_UNIT_ID", "")


def is_sql_mutation(sql_query: str) -> bool:
    cleaned = sql_query.strip().strip(";")
    parsed = sqlparse.parse(cleaned)
    if not parsed:
        return False
    forbidden = {
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "TRUNCATE",
        "PRAGMA",
        "REPLACE",
        "CREATE",
    }
    for stmt in parsed:
        if stmt.get_type() != "SELECT":
            return True
        for token in stmt.flatten():
            if token.value.upper() in forbidden:
                return True
    return False


def _validate_unit(manager_working_unit_id: str) -> str | None:
    unit = (manager_working_unit_id or "").strip()
    if not SESSION_UNIT:
        return "Server session working unit not configured."
    if unit != SESSION_UNIT:
        return (
            f"manager_working_unit_id '{unit}' does not match session scope "
            f"'{SESSION_UNIT}'."
        )
    return None


def _unit_employee_ids(unit: str) -> set[str]:
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute(
        "SELECT employee_id FROM employees WHERE working_unit_id = ?",
        (unit,),
    )
    ids = {row[0] for row in cur.fetchall()}
    conn.close()
    return ids


def _filter_unit_rows(columns: list[str], rows: list, unit: str) -> list:
    if "working_unit_id" in columns:
        idx = columns.index("working_unit_id")
        return [r for r in rows if r[idx] == unit]
    if "employee_id" in columns:
        allowed = _unit_employee_ids(unit)
        idx = columns.index("employee_id")
        return [r for r in rows if r[idx] in allowed]
    return rows


@mcp.tool()
def list_tables() -> str:
    """Discover tables in the workforce planning database."""
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return json.dumps({"status": "success", "tables": tables, "session_unit": SESSION_UNIT})


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Inspect columns for a table."""
    cleaned = table_name.strip().strip("'").strip('"')
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({cleaned});")
    cols = [
        {"cid": r[0], "name": r[1], "type": r[2], "pk": r[5]} for r in cur.fetchall()
    ]
    conn.close()
    if not cols:
        return json.dumps({"status": "error", "message": f"Table '{cleaned}' not found."})
    return json.dumps({"status": "success", "table": cleaned, "columns": cols})


@mcp.tool()
def read_query(sql_query: str, manager_working_unit_id: str) -> str:
    """Run a read-only SELECT. Pass manager_working_unit_id from the logged-in manager."""
    err = _validate_unit(manager_working_unit_id)
    if err:
        return json.dumps({"status": "blocked", "error": err})
    if is_sql_mutation(sql_query):
        return json.dumps(
            {
                "status": "blocked",
                "error": "Mutation queries (DROP, DELETE, UPDATE, INSERT, ...) are prohibited.",
            }
        )
    try:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(sql_query.strip())
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        rows = _filter_unit_rows(columns, rows, manager_working_unit_id)
        conn.close()
        return json.dumps(
            {
                "status": "success",
                "columns": columns,
                "rows": [list(r) for r in rows[:100]],
                "count": len(rows),
                "manager_working_unit_id": manager_working_unit_id,
            }
        )
    except Exception as exc:
        return json.dumps({"status": "error", "message": str(exc)})


@mcp.tool()
def read_policy(policy_file: str) -> str:
    """Read a markdown policy file from policies/ (e.g. shift_scheduling_rules.md)."""
    name = Path(policy_file.strip()).name
    path = POLICIES_DIR / name
    if not path.is_file():
        return json.dumps(
            {"status": "error", "message": f"Policy '{name}' not found in policies/."}
        )
    text = path.read_text(encoding="utf-8")
    return json.dumps({"status": "success", "file": name, "content": text[:20000]})


@mcp.tool()
def drop_table_admin(table_name: str) -> str:
    """Admin-only destructive tool — must be filtered by ADK tool_filter."""
    return f"DANGER: Attempted to drop {table_name}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
