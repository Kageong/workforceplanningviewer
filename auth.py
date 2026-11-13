"""Manager login against SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "enterprise.db"


@dataclass
class ManagerSession:
    manager_id: str
    username: str
    name: str
    working_unit_id: str
    unit_name: str


def authenticate(username: str, db_path: Path | None = None) -> ManagerSession | None:
    """Demo login: manager username only (no password check)."""
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.manager_id, m.username, m.name, m.working_unit_id, w.unit_name
        FROM managers m
        JOIN working_units w ON w.working_unit_id = m.working_unit_id
        WHERE m.username = ? AND m.role = 'Manager'
        """,
        (username.strip(),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return ManagerSession(
        manager_id=row[0],
        username=row[1],
        name=row[2],
        working_unit_id=row[3],
        unit_name=row[4],
    )
