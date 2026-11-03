"""SQLite layer: builds a queryable database from the Pulse data and exposes a read-only connection."""
import sqlite3
from pathlib import Path
from load_data import load_state_category, load_district, load_users, add_period

SCHEMA_DOC = """Tables (SQLite). Quarter ordering: year, quarter. Amounts are in INR.
state_category(state TEXT, year INT, quarter INT, period TEXT, category TEXT /* P2P|Retail|Utility */, txn_count INT)
district(state TEXT, district TEXT, year INT, quarter INT, period TEXT, txn_count INT, txn_amount REAL)
users(state TEXT, year INT, quarter INT, period TEXT, registered_users INT)
state/district values are lowercase, hyphenated for states (e.g. 'tamil-nadu'). period looks like '2026-Q2'."""

def build_db(pulse_root, db_path):
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    load_state_category(pulse_root).pipe(add_period).to_sql("state_category", con, index=False)
    load_district(pulse_root).pipe(add_period).to_sql("district", con, index=False)
    load_users(pulse_root).pipe(add_period).to_sql("users", con, index=False)
    con.execute("CREATE INDEX idx_district ON district(state, district, year, quarter)")
    con.execute("CREATE INDEX idx_sc ON state_category(state, year, quarter)")
    con.commit(); con.close()
    return db_path

def connect_readonly(db_path):
    """Read-only connection: even a crafted query cannot modify data."""
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
