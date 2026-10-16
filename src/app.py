import json
import sqlite3
from flask import Flask, g, jsonify, request, abort

DB_PATH = "grid.db"
app = Flask(__name__)
LEASE_SECONDS = 300

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

#claim come sin with a worker_id and a job_id
#The naive solution is to return a list of selectable jobs to the worker 
#and allow the worker to claim the job. But that means two workers can race. 
@app.post("/claim")
    body = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id")
    if not worker_id:
        abort(400, description="worker_id required")

    con.execute("""
    UPDATE jobs SET state='claimed', worker_id=?, attempt=attempt+1
    WHERE id = (SELECT id FROM jobs WHERE state='pending' LIMIT 1)
    RETURNING id, attempt, payload""",
    (worker_id, LEASE_SECONDS))

if __name__ == "__main__":
    app.run(debug=True)