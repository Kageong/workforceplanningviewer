"""Create and seed data/enterprise.db for the WFP capstone."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "enterprise.db"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


SCHEMA_AND_SEED = """
CREATE TABLE IF NOT EXISTS working_units (
    working_unit_id TEXT PRIMARY KEY,
    unit_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS managers (
    manager_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    working_unit_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Manager',
    FOREIGN KEY (working_unit_id) REFERENCES working_units(working_unit_id)
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    contact_number TEXT,
    email TEXT,
    working_unit_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Employee',
    FOREIGN KEY (working_unit_id) REFERENCES working_units(working_unit_id)
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    shift_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id TEXT NOT NULL,
    leave_type TEXT NOT NULL,
    balance_days REAL NOT NULL,
    as_of_date TEXT NOT NULL,
    PRIMARY KEY (employee_id, leave_type),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    request_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

INSERT OR REPLACE INTO working_units VALUES
    ('WU_NORTH', 'North Plant'),
    ('WU_SOUTH', 'South Plant');

INSERT OR REPLACE INTO managers VALUES
    ('MGR_N001', 'mgr_north', '%(pw_north)s', 'WU_NORTH', 'Alice North', 'Manager'),
    ('MGR_S001', 'mgr_south', '%(pw_south)s', 'WU_SOUTH', 'Bob South', 'Manager');

INSERT OR REPLACE INTO shifts VALUES
    ('SH_N01', 'E_N101', '2026-11-17', '08:00', '16:00'),
    ('SH_N02', 'E_N102', '2026-11-17', '08:00', '16:00'),
    ('SH_N03', 'E_N103', '2026-11-17', '16:00', '00:00'),
    ('SH_N04', 'E_N101', '2026-11-18', '08:00', '16:00'),
    ('SH_N05', 'E_N102', '2026-11-20', '08:00', '16:00'),
    ('SH_S01', 'E_S201', '2026-11-17', '08:00', '16:00'),
    ('SH_S02', 'E_S202', '2026-11-17', '08:00', '16:00'),
    ('SH_S03', 'E_S203', '2026-11-20', '08:00', '16:00');

INSERT OR REPLACE INTO leave_balances VALUES
    ('E_N101', 'Annual', 12.0, '2026-11-01'),
    ('E_N102', 'Annual', 8.5, '2026-11-01'),
    ('E_N103', 'Annual', 15.0, '2026-11-01'),
    ('E_S201', 'Annual', 10.0, '2026-11-01'),
    ('E_S202', 'Annual', 6.0, '2026-11-01'),
    ('E_S203', 'Annual', 14.0, '2026-11-01');

INSERT OR REPLACE INTO leave_requests VALUES
    ('LR_N01', 'E_N101', 'Annual', '2026-11-25', '2026-11-26', 'Pending'),
    ('LR_N02', 'E_N103', 'Annual', '2026-11-10', '2026-11-12', 'Approved'),
    ('LR_S01', 'E_S201', 'Annual', '2026-11-22', '2026-11-24', 'Pending');
"""


EMPLOYEES = [
    ("E_N101", "Nina Patel", "+60123451001", "nina.patel@corp.local", "WU_NORTH", "Employee"),
    ("E_N102", "James Wong", "+60198765402", "james.wong@corp.local", "WU_NORTH", "Employee"),
    ("E_N103", "Siti Rahman", "+60135551203", "siti.rahman@corp.local", "WU_NORTH", "Employee"),
    ("E_S201", "David Lee", "+60187654304", "david.lee@corp.local", "WU_SOUTH", "Employee"),
    ("E_S202", "Maria Gomez", "+60124681305", "maria.gomez@corp.local", "WU_SOUTH", "Employee"),
    ("E_S203", "Omar Hassan", "+60131415906", "omar.hassan@corp.local", "WU_SOUTH", "Employee"),
]


def _upsert_employees(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO employees
        (employee_id, name, contact_number, email, working_unit_id, role)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        EMPLOYEES,
    )


def _migrate_employee_contacts(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(employees)")
    cols = {row[1] for row in cur.fetchall()}
    if "contact_number" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN contact_number TEXT")
    if "email" not in cols:
        cur.execute("ALTER TABLE employees ADD COLUMN email TEXT")
    _upsert_employees(conn)


def bootstrap(db_path: Path | None = None) -> Path:
    db_path = db_path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA_AND_SEED % {
        "pw_north": _hash_password("north123"),
        "pw_south": _hash_password("south123"),
    }
    conn = sqlite3.connect(db_path)
    conn.executescript(sql)
    _migrate_employee_contacts(conn)  # columns + employee seed/upsert
    conn.commit()
    conn.close()
    return db_path


def ensure_db(db_path: Path | None = None) -> Path:
    """Create DB if missing; otherwise apply lightweight migrations only."""
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return bootstrap(db_path)
    conn = sqlite3.connect(db_path)
    _migrate_employee_contacts(conn)
    conn.commit()
    conn.close()
    return db_path


if __name__ == "__main__":
    path = bootstrap()
    print(f"Bootstrapped {path}")
