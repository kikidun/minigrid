import sqlite3
import config
import requests 
import time
import logging
import jsonlog

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
    jsonlog.setup("sweeper")
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
                    logging.debug("Healthy, sweep ok!")
                    should_sweep = True
                else:
                    logging.debug("Healthy, no sweep!") 
            elif response.status_code == 503:
                logging.warning("DB down!")
            else:
                logging.warning(f"Unexpected status code {response.status_code} received!")
        except requests.RequestException:
            logging.warning("Endpoint unreachable!")

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
                        logging.debug("Nothing to sweep")
                        finished = True
                        con.execute("""COMMIT""")
                    else:
                        context = {"job_id": row["job_id"], "attempt_number": row["attempt_number"]}
                        #/claim increments the attempt_number
                        if row["attempt_number"] >= 3:
                            logging.warning(f"job {row["job_id"]} reached attempt threshold, sending to DLQ", extra=context)
                            new_state = 'dlq'
                            error = f"max_attempts_exceeded: {row['error'] or 'lease_expired'}"
                            finished_at = now
                        else:
                            logging.info(f"job {row["job_id"]} moving from {row["job_state"]} to the pending pool", extra=context)
                            new_state = 'pending'
                            error = None
                            finished_at = None
                        #run the job table update and the attempt table update
                        job_response = job_table_update(new_state, finished_at, error, row["job_id"], now, row["attempt_number"])
                        if job_response.rowcount == 0:                 
                            logging.warning(f"failed to update job_status to {new_state} for job {row["job_id"]}", extra=context)
                            con.execute("""ROLLBACK""")
                            finished = True
                        elif job_response.rowcount == 1:
                            logging.info(f"job {row["job_id"]} sent to {new_state}", extra=context)
                            if row["job_state"] == 'failed':
                                con.execute("""COMMIT""")
                                continue
                            attempts_response = attempt_lease_expired_update(now, row["job_id"], row["attempt_number"])
                            if attempts_response.rowcount == 0:                 
                                logging.warning(f"failed to update attempt outcome to {new_state} for job {row["job_id"]} attempt {row["attempt_number"]}", extra=context)
                                con.execute("""ROLLBACK""")
                                finished = True
                            elif attempts_response.rowcount == 1:
                                logging.info(f"job {row["job_id"]} attempt {row["attempt_number"]} marked expired", extra=context)
                                con.execute("""COMMIT""")

                except sqlite3.Error:
                    if con.in_transaction:
                        con.execute("""ROLLBACK""")
                    finished = True
                    logging.exception("sweep failed")
            time.sleep(10)
        else:
            time.sleep(10)