MAX_ATTEMPTS = 3

def complete_job(con, job_id, worker_id):
    with con:
        cur = con.execute("""
            UPDATE jobs
            SET job_state = 'complete',
                finished_at = unixepoch(),
                error = NULL
            WHERE id = ? AND worker_id = ? AND job_state = 'running'
        """, (job_id, worker_id))
    return cur.rowcount == 1


def fail_job(con, job_id, worker_id, error):
    with con:
        cur = con.execute("""
            UPDATE jobs
            SET job_state = CASE WHEN attempts >= ? THEN 'dlq' ELSE 'failed' END,
                finished_at = unixepoch(),
                error = ?
            WHERE id = ? AND worker_id = ? AND job_state = 'running'
        """, (MAX_ATTEMPTS, error, job_id, worker_id))
    return cur.rowcount == 1

#How do I want claim job to work? I want the worker to ask for claimable jobs and then to pick a claimable job and send the claim transaction. 
#Or rather, I want it to hit the claim endpoint to claim the transaction. 
def claim_job(con, worker_id, job_id):
    with con:
        cur = con.execute("""
            UPDATE jobs
            SET job_state = 'claimed',
                lease_initiated = unixepoch(),
                last_progress = unixepoch(),
                error = NULL
            WHERE id = ? AND worker_id = ? AND job_state = 'pending'
        """, (job_id, worker_id))
    return cur.rowcount == 1