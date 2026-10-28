import sqlite3
import config
import requests 
import time

def sweep():
    return

def job_table_update(new_state, error, job_id, now, attempt_number):
    job_response = con.execute("""
        UPDATE jobs
        SET job_state = ?, 
            finished_at = NULL, 
            worker_id = NULL, 
            lease_initiated = NULL, 
            lease_expiry = NULL, 
            last_progress = NULL,
            error = ?
        WHERE id = ?
            AND job_state IN ('claimed', 'running')
            AND lease_expiry < ?
            AND attempt_number = ?
        """,(new_state, error, job_id, now, attempt_number))
    return job_response

def attempt_lease_expired_update(now, job_id, attempt_number):
    #Update the attempts table
    attempts_response = con.execute("""
        UPDATE attempts
        SET outcome = 'died', 
            error = 'lease_expired',
            ended_at = ?
        WHERE job_id = ? 
            AND attempt_number = ?
            AND outcome = 'running'
        """,(now, job_id, attempt_number))
    return attempts_response

if __name__ == "__main__":
    con = config.connect()
    while True:
        should_sweep = False
        try:
            response = requests.get(config.API_URL + "/health", timeout=2)
            if response.status_code == 200:
                if response.json()["sweep_ok"]:
                    print("Healthy, sweep ok!")
                    should_sweep = True
                else:
                    print("Healthy, no sweep!") 
            elif response.status_code == 503:
                print("DB down!")
            else:
                print(f"Unexpected status code {response.status_code} received!")
        except requests.RequestException:
            print("Endpoint unreachable!")

        if should_sweep:
            finished = False
            while not finished:
                now = time.time_ns() // 1_000_000
                try:
                    con.execute("BEGIN IMMEDIATE")
                    row = con.execute("""
                        SELECT id AS job_id, attempt_number FROM jobs WHERE job_state IN ('claimed', 'running') 
                        AND lease_expiry < ?
                        ORDER BY lease_expiry LIMIT 1
                    """,(now,)).fetchone()
                    if row is None:
                        print("Nothing to sweep")
                        finished = True
                        con.execute("""COMMIT""")
                    else:
                        if row["attempt_number"] >= 3:
                            print(f"job {row["job_id"]} reached attempt theshold, sending to DLQ")
                            new_state = 'dlq'
                            error = 'max_attempts_exceeded'
                        else:
                            print(f"job {row["job_id"]} lease expired, returning to the pending pool")
                            new_state = 'pending'
                            error = None
                        job_response = job_table_update(new_state, error, row["job_id"], now, row["attempt_number"])
                        if job_response.rowcount == 0:                 
                            print(f"failed to update job_status to {new_state} for job {row["job_id"]}")
                            con.execute("""ROLLBACK""")
                            finished = True
                        elif job_response.rowcount == 1:
                            print(f"job {row["job_id"]} sent to {new_state}")
                            attempts_response = attempt_lease_expired_update(now, row["job_id"], row["attempt_number"])
                            if attempts_response.rowcount == 0:                 
                                print(f"failed to update attempt outcome to {new_state} for job {row["job_id"]} attempt {row["attempt_number"]}")
                                con.execute("""ROLLBACK""")
                                finished = True
                            elif attempts_response.rowcount == 1:
                                print(f"job {row["job_id"]} attempt {row["attempt_number"]} marked expired")
                                con.execute("""COMMIT""")

                except sqlite3.Error as e:
                    if con.in_transaction:
                        con.execute("""ROLLBACK""")
                    finished = True
                    print(f"sweep failed, error message: {e}")
            time.sleep(10)
        else:
            time.sleep(10)