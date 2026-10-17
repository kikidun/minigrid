import sqlite3
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR.parent / "db" / "grid.db"
API_URL = os.environ.get("API_URL", "http://127.0.0.1:5000")

def connect():
    con = sqlite3.connect(DB_PATH, isolation_level=None, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con