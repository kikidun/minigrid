import logging
import threading
import time
import requests
import json
import random
import socket
import jsonlog
import config
import os
from uuid import uuid4
from payload import run_var, JobCancelled

HEARTBEAT_INTERVAL = 10
url = config.API_URL
claim_url = url + "/claim"
heartbeat_url = url + "/heartbeat"
complete_url = url + "/complete"
fail_url = url + '/fail'
hostname = socket.gethostname()
worker_id = os.environ.get("NODE_NAME", hostname) + '-' + uuid4().hex[:6]


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
    context = {"job_id": job["job_id"], "attempt_number": job["attempt_number"]}
    logging.info("Heartbeat thread for job %s: starting", job["job_id"], extra=context)
    while not job_done.wait(HEARTBEAT_INTERVAL):
        try:
            response = send_heartbeat(worker_id, job["job_id"], job["attempt_number"])
        except requests.RequestException as e:
            logging.warning("Heartbeat exception %s", e, extra=context)
            continue
        if response.status_code == 204:
            logging.debug("Heartbeat sent", extra=context)
        elif response.status_code == 409:
            logging.warning("lease expired", extra=context)
            lease_lost.set()
            return

def backoff_with_jitter(attempt, base_delay=1, cap=32):
    # Calculate exponential backoff
    calculated_delay = min(cap, base_delay * (2 ** attempt))
    
    # Apply Full Jitter: pick a random float between 0 and calculated_delay
    jitter_delay = random.uniform(0, calculated_delay)
    
    return jitter_delay

def check_lease(fraction):
    logging.debug("progress %.0f%%", fraction * 100, extra=context)
    if lease_lost.is_set():
        logging.warning("lease lost at %.0f%%, cancelling", fraction * 100, extra=context)
        raise JobCancelled()
if __name__ == "__main__":
    jsonlog.setup("worker", worker_id)
    attempt = 0
    while True:
        #call /claim
        error = None
        try:
            response = claim_job()
            if response.status_code == 200:
                job = response.json()
                context = {"job_id": job["job_id"], "attempt_number": job["attempt_number"]}
                logging.info("Job %s picked up", job["job_id"], extra=context)
                #reset backoff after success
                attempt = 0
                #do the job
                #create fresh events
                job_done = threading.Event()
                lease_lost = threading.Event()

                #start the heartbeat
                heartbeat = threading.Thread(target=heartbeat_function, args=(worker_id, job_done, lease_lost, job))
                heartbeat.start()

                #job loop 
                try:
                    result = run_var(job["params"], progress=check_lease, chunk_size=max(1, job["params"]["n_sims"] // 20))
                except JobCancelled:
                    logging.info("lease_lost for job %s, dropping job", job["job_id"], extra=context)
                except Exception as e:
                    error = f"{type(e).__name__}: {e}"
                    logging.exception("job %s failed", job["job_id"], extra=context)

                job_done.set()
                heartbeat.join()

                #post-job
                #check lease_lost
                if lease_lost.is_set():
                    logging.info("lease_lost for job %s, dropping job", job["job_id"], extra=context)
                    continue
                

                #if job raised an error
                if error is not None:
                    #hit the /fail endpoint
                    logging.info("job %s failed", job["job_id"], extra=context)
                    for try_num in range(5):
                        try:
                            fail = fail_job(worker_id, job["job_id"], job["attempt_number"], error)
                        except requests.RequestException as e:
                            logging.warning("Failure exception %s", e, extra=context)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time, extra=context)
                            time.sleep(sleep_time)
                            continue
                        if fail.status_code == 204: 
                            logging.info("failure call returned %s", fail.status_code, extra=context)
                            break
                        elif fail.status_code == 409:
                            logging.info("failure call returned %s", fail.status_code, extra=context)
                            logging.warning("worker is not owner of job %s tossing", job["job_id"], extra=context)
                            break
                        elif fail.status_code >= 500:
                            logging.info("failure call returned %s", fail.status_code, extra=context)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time, extra=context)
                            time.sleep(sleep_time)
                        else:
                            logging.info("failure call returned status_code %s", fail.status_code, extra=context)
                            logging.info("failure call returned response %s", fail.text, extra=context)
                            break
                    else:
                        logging.error("gave up failing job %s", job["job_id"], extra=context)
                else:
                    #hit the /complete endpoint
                    logging.info("job %s complete", job["job_id"], extra=context)
                    for try_num in range(5):
                        try:
                            complete = complete_job(worker_id, job["job_id"], job["attempt_number"], result)
                        except requests.RequestException as e:
                            logging.warning("Completion exception %s", e, extra=context)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time, extra=context)
                            time.sleep(sleep_time)
                            continue
                        if complete.status_code == 204: 
                            logging.info("completion call returned %s", complete.status_code, extra=context)
                            break
                        elif complete.status_code == 409:
                            logging.info("completion call returned %s", complete.status_code, extra=context)
                            logging.warning("worker is not owner of job %s tossing", job["job_id"], extra=context)
                            break
                        elif complete.status_code >= 500:
                            logging.info("completion call returned %s", complete.status_code, extra=context)
                            sleep_time = 5 + (try_num * 3)
                            logging.info("sleeping %ss to try again", sleep_time, extra=context)
                            time.sleep(sleep_time)
                        else:
                            logging.info("completion call returned status_code %s", complete.status_code, extra=context)
                            logging.info("completion call returned response %s", complete.text, extra=context)
                            break
                    else:
                        logging.error("gave up completing job %s", job["job_id"], extra=context)

            #no job? sleep with jitter
            elif response.status_code == 204:
                attempt = 0
                sleep_time = 5 + random.uniform(0, 1)
                logging.debug("no claimable jobs, sleeping for %s seconds", sleep_time)
                time.sleep(sleep_time)
                continue
            elif response.status_code >= 500:
                logging.warning("claim call returned %s", response.status_code)
                sleep_time = 5 + random.uniform(0, 1)
                logging.info("sleeping %ss to try again", sleep_time)
                time.sleep(sleep_time)

        #connection error? backoff
        except requests.RequestException:
            logging.warning("Endpoint unreachable!")
            attempt += 1
            jitter = backoff_with_jitter(attempt)
            logging.warning("Attempt number %s, connection issue, sleeping for %s seconds", attempt, 10 + jitter)
            time.sleep(10 + jitter)
            continue