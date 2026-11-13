# Purpose: Smoke-test MCP read_query unit scoping.
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["WFP_WORKING_UNIT_ID"] = "WU_NORTH"

from mcp_wfp_server import list_tables, read_query, describe_table

print(list_tables())
print(describe_table("employees"))
print(
    read_query(
        "SELECT employee_id, name FROM employees",
        "WU_NORTH",
    )
)
blocked = read_query("DELETE FROM employees", "WU_NORTH")
print(blocked)
assert json.loads(blocked)["status"] == "blocked"
wrong = read_query("SELECT * FROM employees", "WU_SOUTH")
print(wrong)
assert json.loads(wrong)["status"] == "blocked"
print("mcp_smoke_ok")
