import sqlite3
import config
import requests 
import time

def sweep():
    return

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
                    con.execute("""COMMIT""")
                else:
                    #DLQ check
                    if row["attempt_number"] >= 5:
                        print(f"job {row["job_id"]} reached attempt theshold, sending to DLQ")
                        #Update the jobs table
                        job_response = con.execute("""
                            UPDATE jobs
                            SET job_state = 'dlq', 
                                finished_at = NULL, 
                                worker_id = NULL, 
                                lease_initiated = NULL, 
                                lease_expiry = NULL, 
                                last_progress = NULL,
                                error = 'lease_expired'
                            WHERE id = ?
                                AND job_state IN ('claimed', 'running')
                                AND lease_expiry < ?
                                AND attempt_number = ?
                            """,(row["job_id"], now, row["attempt_number"]))
                            
                        #check job rowcount
                        if job_response.rowcount == 0:                 
                            print(f"failed to update job_status for job {row["job_id"]}")
                            con.execute("""ROLLBACK""")
                        elif job_response.rowcount == 1:
                            print(f"job {row["job_id"]} sent to DLQ")

                            #Update the attempts table
                            attempts_response = con.execute("""
                                UPDATE attempts
                                SET outcome = 'died', 
                                    error = 'lease_expired',
                                    ended_at = ?
                                WHERE job_id = ? AND attempt_number = ?
                                """,(now, row["job_id"], row["attempt_number"]))

                            #check attempt rowcount
                            if attempts_response.rowcount == 0:                 
                                print(f"failed to update attempt outcome for job {row["job_id"]} attempt {row["attempt_number"]}")
                                con.execute("""ROLLBACK""")
                            elif attempts_response.rowcount == 1:
                                print(f"job {row["job_id"]} attempt {row["attempt_number"]} marked expired")
                                con.execute("""COMMIT""")
            except sqlite3.Error as e:
                if con.in_transaction:
                    con.execute("""ROLLBACK""")
                print(f"sweep failed, error message: {e}")

            time.sleep(10)
        else:
            time.sleep(10)