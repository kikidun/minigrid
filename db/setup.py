import sqlite3

con = sqlite3.connect("grid.db")
con.row_factory = sqlite3.Row          # rows act like dicts
con.execute("PRAGMA foreign_keys = ON")  # off by default, turn it on

con.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        job_state TEXT,
        worker_id TEXT UNIQUE,
        lease_initiated INTEGER,
        last_progress INTEGER,
        error TEXT,
        attempt_count INTEGER,
        attempt_id INTEGER UNIQUE
    )
""")

""" # Always parameterize. Never f-string values into SQL.
with con:  # commits on success, rolls back on exception
    con.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Ada", "ada@x.com"))
    con.executemany("INSERT INTO users (name, email) VALUES (?, ?)",
                    [("Bob", "b@x.com"), ("Cy", "c@x.com")])

for row in con.execute("SELECT * FROM users WHERE name LIKE ?", ("A%",)):
    print(row["name"], row["email"]) """

con.close()