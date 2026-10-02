import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DB_PATH = os.environ.get("LOAN_DB", "loan_tracker.db")


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may run a request's code in different threads.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row            # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys unless asked
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the tables from schema.sql if they don't exist yet."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='borrowers'"
    ).fetchone()
    if not exists:
        conn.executescript(SCHEMA_PATH.read_text())


def get_db():
    """FastAPI dependency: one connection per request, always closed afterwards."""
    conn = connect()
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()
