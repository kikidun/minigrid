import logging
import threading
import time
import requests
import json
import random
import socket
from uuid import uuid4
from payload import run_var, JobCancelled

HEARTBEAT_INTERVAL = 10
url = "http://127.0.0.1:5000"
claim_url = url + "/claim"
heartbeat_url = url + "/heartbeat"
complete_url = url + "/complete"
fail_url = url + '/fail'
hostname = socket.gethostname()
worker_id = hostname + '-' + uuid4().hex[:6]


def claim_job():
    payload = json.dumps({
        "worker_id": worker_id
    })
    headers = {
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", claim_url, headers=headers, data=payload, timeout=5)

    logging.debug(response.text)
    return response

def send_heartbeat(worker_id, job_id, attempt_number):
    payload = json.dumps({
        "worker_id": worker_id,
        "job_id": job_id,
        "attempt_number": attempt_number
    })
    headers = {
      'Content-Type': 'application/json'
    }
    response = requests.request("POST", heartbeat_url, headers=headers, data=payload, timeout=5)
    logging.debug(response.text)
    return response

def complete_job(worker_id, job_id, attempt_number, result):
    payload = json.dumps({
        "worker_id": worker_id,
        "job_id": job_id,
        "attempt_number": attempt_number,
        "result": result
    })
    headers = {
      'Content-Type': 'application/json'
    }
    response = requests.request("POST", complete_url, headers=headers, data=payload, timeout=5)
    logging.debug(response.text)
    return response

def fail_job(worker_id, job_id, attempt_number, error):
    payload = json.dumps({
        "worker_id": worker_id,
        "job_id": job_id,
        "attempt_number": attempt_number,
        "error": error
    })
    headers = {
      'Content-Type': 'application/json'
    }
    response = requests.request("POST", fail_url, headers=headers, data=payload, timeout=5)
    logging.debug(response.text)
    return response

def heartbeat_function(worker_id, job_done, lease_lost, job):
    logging.info("Heartbeat thread for job %s: starting", job["job_id"])
    while not job_done.wait(HEARTBEAT_INTERVAL):
        try:
            response = send_heartbeat(worker_id, job["job_id"], job["attempt_number"])
        except requests.RequestException as e:
            logging.info("Heartbeat exception %s", e)
            continue
        if response.status_code == 204:
            logging.info("Heartbeat sent")
        elif response.status_code == 409:
            logging.info("lease expired")
            lease_lost.set()
            return

def backoff_with_jitter(attempt, base_delay=1, cap=32):
    # Calculate exponential backoff
    calculated_delay = min(cap, base_delay * (2 ** attempt))
    
    # Apply Full Jitter: pick a random float between 0 and calculated_delay
    jitter_delay = random.uniform(0, calculated_delay)
    
    return jitter_delay

def check_lease(fraction):
    logging.info("progress %.0f%%", fraction * 100)
    if lease_lost.is_set():
        logging.info("lease lost at %.0f%%, cancelling", fraction * 100)
        raise JobCancelled()
if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO,
                        datefmt="%H:%M:%S")
    logging.info("Main    : before creating thread")

    attempt = 0
    while True:
        #call /claim
        error = None
        try:
            response = claim_job()
            if response.status_code == 200:
                job = response.json()
                logging.info("Job %s picked up", job["job_id"])
                #reset backoff after success
                attempt = 0
                #do the job
                #create fresh events
                job_done = threading.Event()
                lease_lost = threading.Event()

                #start the heartbeat
                heartbeat = threading.Thread(target=heartbeat_function, args=(worker_id, job_done, lease_lost, job))
                logging.info("Main    : before running thread")
                heartbeat.start()

                #job loop 
                try:
                    result = run_var(job["params"], progress=check_lease, chunk_size=max(1, job["params"]["n_sims"] // 20))
                except JobCancelled:
                    logging.info("lease_lost for job %s, dropping job", job["job_id"])
                except Exception as e:
                    error = f"{type(e).__name__}: {e}"
                    logging.exception("job %s failed", job["job_id"])

                job_done.set()
                heartbeat.join()

                #post-job
                #check lease_lost
                if lease_lost.is_set():
                    logging.info("lease_lost for job %s, dropping job", job["job_id"])
                    continue
                

                #if job raised an error
                if error is not None:
                    #hit the /fail endpoint
                    logging.info("job %s failed", job["job_id"])
                    for try_num in range(5):
                        try:
                            fail = fail_job(worker_id, job["job_id"], job["attempt_number"], error)
                        except requests.RequestException as e:
                            logging.info("Failure exception %s", e)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time)
                            time.sleep(sleep_time)
                            continue
                        if fail.status_code == 204: 
                            logging.info("failure call returned %s", fail.status_code)
                            break
                        elif fail.status_code == 409:
                            logging.info("failure call returned %s", fail.status_code)
                            logging.info("worker is not owner of job %s tossing", job["job_id"])
                            break
                        elif fail.status_code >= 500:
                            logging.info("failure call returned %s", fail.status_code)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time)
                            time.sleep(sleep_time)
                        else:
                            logging.info("failure call returned status_code %s", fail.status_code)
                            logging.info("failure call returned response %s", fail.text)
                            break
                    else:
                        logging.error("gave up failing job %s", job["job_id"])
                else:
                    #hit the /complete endpoint
                    logging.info("job %s complete", job["job_id"])
                    for try_num in range(5):
                        try:
                            complete = complete_job(worker_id, job["job_id"], job["attempt_number"], result)
                        except requests.RequestException as e:
                            logging.info("Completion exception %s", e)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time)
                            time.sleep(sleep_time)
                            continue
                        if complete.status_code == 204: 
                            logging.info("completion call returned %s", complete.status_code)
                            break
                        elif complete.status_code == 409:
                            logging.info("completion call returned %s", complete.status_code)
                            logging.info("worker is not owner of job %s tossing", job["job_id"])
                            break
                        elif complete.status_code >= 500:
                            logging.info("completion call returned %s", complete.status_code)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time)
                            time.sleep(sleep_time)
                        else:
                            logging.info("completion call returned status_code %s", complete.status_code)
                            logging.info("completion call returned response %s", complete.text)
                            break
                    else:
                        logging.error("gave up completing job %s", job["job_id"])

            #no job? sleep with jitter
            elif response.status_code == 204:
                attempt = 0
                sleep_time = 5 + random.uniform(0, 1)
                logging.info("no claimable jobs, sleeping for %s seconds", sleep_time)
                time.sleep(sleep_time)
                continue
            elif response.status_code >= 500:
                logging.info("claim call returned %s", response.status_code)
                sleep_time = 5 + random.uniform(0, 1)
                logging.info("sleeping %ss to try again", sleep_time)
                time.sleep(sleep_time)

        #connection error? backoff
        except requests.RequestException:
            logging.info("Endpoint unreachable!")
            attempt += 1
            jitter = backoff_with_jitter(attempt)
            logging.info("Attempt number %s, connection issue, sleeping for %s seconds", attempt, 10 + jitter)
            time.sleep(10 + jitter)
            continue