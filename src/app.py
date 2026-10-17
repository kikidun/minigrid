import json
import time
import sqlite3
from flask import Flask, g, jsonify, request, abort

DB_PATH = "../db/grid.db"
app = Flask(__name__)
LEASE_SECONDS = 300
start_time = time.monotonic()
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
    now_ms = time.time_ns() // 1_000_000
    try:
        con.execute("BEGIN IMMEDIATE")
        cursor = con.execute("""
        UPDATE jobs SET job_state='claimed', worker_id=?, attempt_number=attempt_number+1, lease_initiated=?, lease_expiry=?
        WHERE id = (SELECT id FROM jobs WHERE job_state='pending' LIMIT 1)
        RETURNING id, attempt_number, params""",(worker_id, now_ms, now_ms + LEASE_SECONDS*1000)).fetchone()

        if cursor is None:                 
            con.execute("ROLLBACK")
            return "", 204

        con.execute("""
        INSERT INTO attempts (job_id, worker_id, started_at, outcome, attempt_number) VALUES (?, ?, ?, ?, ?)""",
        (cursor["id"], worker_id, now_ms, 'running', cursor["attempt_number"]))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return jsonify({                    
        "job_id": cursor["id"],
        "attempt_number": cursor["attempt_number"],
        "params": json.loads(cursor["params"]),
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
    now_ms = time.time_ns() // 1_000_000

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


@app.post("/complete")
def complete():
    #takes job_id, worker_id, attempt_number, result
    #job table gets complete with result and finished_at
    #attempt table gets outcome, and ended at
    body = request.get_json(silent=True) or {}
    job_id = body.get("job_id")
    attempt_number = body.get("attempt_number")
    worker_id = body.get("worker_id")
    result = body.get("result")

    if not worker_id:
        abort(400, description="worker_id required")
    if not job_id:
        abort(400, description="job_id required")
    if not attempt_number:
        abort(400, description="attempt_number required")
    if result is None:
        abort(400, description="result required")

    #atomic transaction
    
    
    con = get_db()
    now_ms = time.time_ns() // 1_000_000
    try:
        con.execute("BEGIN IMMEDIATE")
        #job table gets complete with result and finished_at
        cursor = con.execute("""
        UPDATE jobs
        SET job_state = 'complete', finished_at = ?, result=?
        WHERE id = ?
            AND attempt_number = ?
            AND worker_id = ?
            AND job_state IN ('claimed', 'running')""",(now_ms, json.dumps(result), job_id, attempt_number, worker_id))

        if cursor.rowcount == 0:                
            con.execute("ROLLBACK")
            return "", 409

        #attempt table gets outcome, and ended at
        cursor = con.execute("""
        UPDATE attempts
        SET outcome = 'succeeded', ended_at = ?
        WHERE job_id = ? AND attempt_number = ? AND outcome = 'running'""",
        (now_ms, job_id, attempt_number))

        if cursor.rowcount == 0:
            con.execute("ROLLBACK")                 
            return "", 500            

        con.execute("COMMIT")
        return "", 204

    except Exception:
        con.execute("ROLLBACK")
        raise

@app.get("/health")
def health():
    if time.monotonic() - start_time > 60.0:
        return "{'sweep_ok': true}", 200
    else:
        return "{'sweep_ok': false}", 200


if __name__ == "__main__":
    app.run(debug=True)