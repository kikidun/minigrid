import json
import time
import sqlite3
from flask import Flask, g, jsonify, request, abort

DB_PATH = "../db/grid.db"
app = Flask(__name__)
LEASE_SECONDS = 300

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, isolation_level=None, timeout=5)
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
def claim():
    body = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id")
    if not worker_id:
        abort(400, description="worker_id required")

    con = get_db()
    now_ms = milliseconds = time.time_ns() // 1_000_000
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("""
        UPDATE jobs SET job_state='claimed', worker_id=?, attempt_number=attempt_number+1, lease_initiated=?, lease_expiry=?
        WHERE id = (SELECT id FROM jobs WHERE job_state='pending' LIMIT 1)
        RETURNING id, attempt_number, params""",(worker_id, now_ms, now_ms + LEASE_SECONDS*1000)).fetchone()

        if row is None:                 
            con.execute("ROLLBACK")
            return "", 204

        con.execute("""
        INSERT INTO attempts (job_id, worker_id, started_at, outcome, attempt_number) VALUES (?, ?, ?, ?, ?)""",
        (row["id"], worker_id, now_ms, 'running', row["attempt_number"]))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return jsonify({                    
        "job_id": row["id"],
        "attempt_number": row["attempt_number"],
        "params": json.loads(row["params"]),
    })

@app.post("/heartbeat")
def heartbeat():
    #gonna take worker id, job id and attempt number
    body = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id")
    job_id = body.get("job_id")
    attempt_number = body.get("attempt_number")
    if not worker_id:
        abort(400, description="worker_id required")
    if not job_id:
        abort(400, description="job_id required")
    if not attempt_number:
        abort(400, description="attempt_number required")

    con = get_db()
    now_ms = milliseconds = time.time_ns() // 1_000_000

    try:
        cursor = con.execute("""
        UPDATE jobs
        SET job_state = 'running',
        lease_expiry = ?
        WHERE id = ?
            AND attempt_number = ?
        AND worker_id = ?
        AND job_state IN ('claimed', 'running')
        """, (now_ms + 45_000, job_id, attempt_number, worker_id))

        if cursor.rowcount == 0:                 
            return "", 409
        elif cursor.rowcount == 1:
            return "", 204
    except Exception:
        con.execute("ROLLBACK")
        raise

if __name__ == "__main__":
    app.run(debug=True)