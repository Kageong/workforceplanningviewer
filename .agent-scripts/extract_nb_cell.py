# Purpose: Extract MCP/guardrail cells from course notebook template.
# Triggered by: capstone implementation start.

import json
from pathlib import Path

nb_path = Path(r"C:\Users\okg1\Downloads\[YuhKang]_true_mcp_protocol_streamlit_participants.ipynb")
nb = json.loads(nb_path.read_text(encoding="utf-8"))
keywords = ("is_sql_mutation", "before_model_guardrail", "after_model")
for i, cell in enumerate(nb["cells"]):
    src = "".join(cell.get("source", []))
    if any(k in src for k in keywords):
        print(f"=== CELL {i} ({len(src)} chars) ===")
        print(src)
        print()
