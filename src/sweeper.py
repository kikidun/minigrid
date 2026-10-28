import sqlite3
import config
import requests 
import time

#Sweeper is responsible for finding jobs with expired leases and moving them back to pending or into the DLQ
#Runs as it's own process to not block the API

def job_table_update(new_state, finished_at, error, job_id, now, attempt_number):
    #updates the job table if the attempt number matches whats currently running to prevent zombie updates
    job_response = con.execute("""
        UPDATE jobs
        SET job_state = ?, 
            finished_at = ?, 
            worker_id = NULL, 
            lease_initiated = NULL, 
            lease_expiry = NULL, 
            last_progress = NULL,
            error = ?
        WHERE id = ? 
        AND ((job_state IN ('claimed', 'running') AND lease_expiry < ?) 
            OR job_state = 'failed') 
        AND attempt_number = ?
        """,(new_state, finished_at, error, job_id, now, attempt_number))
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
        """
        Primary loop
        Checks the /health endpoint for availability and for grace period
        On API startup, all jobs have 60 seconds to heartbeat before leases start expiring
        """

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
                #Inner loop to do the sweeping
                now = time.time_ns() // 1_000_000
                try:
                    #Acquire write lock before checking for jobs to update and updating them
                    #a worker heartbeat can't land between the SELECT and the UPDATEs
                    con.execute("BEGIN IMMEDIATE")
                    #1 job at a time, short transaction, and allows the "list" to keep updating
                    row = con.execute("""
                        SELECT id AS job_id, attempt_number, job_state, error FROM jobs WHERE (job_state IN ('claimed', 'running') 
                        AND lease_expiry < ?) OR job_state = 'failed'
                        ORDER BY lease_expiry LIMIT 1
                    """,(now,)).fetchone()
                    if row is None:
                        print("Nothing to sweep")
                        finished = True
                        con.execute("""COMMIT""")
                    else:
                        #/claim increments the attempt_number
                        if row["attempt_number"] >= 3:
                            print(f"job {row["job_id"]} reached attempt theshold, sending to DLQ")
                            new_state = 'dlq'
                            error = f"max_attempts_exceeded: {row['error'] or 'lease_expired'}"
                            finished_at = now
                        else:
                            print(f"job {row["job_id"]} moving from {row["job_state"]} to the pending pool")
                            new_state = 'pending'
                            error = None
                            finished_at = None
                        #run the job table update and the attempt table update
                        job_response = job_table_update(new_state, finished_at, error, row["job_id"], now, row["attempt_number"])
                        if job_response.rowcount == 0:                 
                            print(f"failed to update job_status to {new_state} for job {row["job_id"]}")
                            con.execute("""ROLLBACK""")
                            finished = True
                        elif job_response.rowcount == 1:
                            print(f"job {row["job_id"]} sent to {new_state}")
                            if row["job_state"] == 'failed':
                                con.execute("""COMMIT""")
                                continue
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