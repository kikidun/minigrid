first sweeper pass:

one pass will first check the table for jobs with their leases expired, or in the failed state.
with that list of jobs,
for expired jobs, it will mark them as pending, can probably leave the lease and progress info since it gets set, but cleaning it up might be tidy. we can also update the attempts table with outcome, and ended at.
for failed jobs, we first check if the attempts has breached the threshold for dlq, and if not we do the above.

we need to:
clear lease columns
do the DLQ check
consider failure, why not let the worker fail?
address race condition in list then process 

Second sweeper logic pass:
Phase 1: Startup/Interval
Sleep for 1 min
Phase 2: Sweep
run until complete:
    grab a job that is failed or expired:
        evaluate attempts for DLQ qualification:
            send to DLQ
        otherwise:
            set job_state to pending, set finished_at, worker_id, lease_initiated, last_progress to NULL

separate grace from sweeper interval
    when the API starts up, it extends expiry times for running jobs
    MAX(lease_expiry, startup_time + 60s)
close transaction timing


Third sweeper logic pass:
run until complete:
    BEGIN IMMEDIATE
    SELECT oldest expired job LIMIT 1:
        if none:
            rollback and sleep
        otherwise:
            evaluate attempts for DLQ qualification:
                send to DLQ with error 
            otherwise:
                UPDATE jobs > set job_state to pending, set finished_at, worker_id, lease_initiated, lease_expiry, last_progress to NULL WHERE lease_expiry < ? AND attempt_number = ?
                UPDATE attempts > set outcome to lost, set error to lease-expired, ended_at to now
    COMMIT
thought: The sweeper could be a job itself. The API could store its startup time in the sweeper's lease initiated time and could update the last progress column with a heartbeat of its own. The sweeper could start up and do a grace check to see if the API has been up for at least a minute, or to see if the API has been down for too long.
    but it doesn't have any params, and the CHECKS assume worker style semantics
    don't wanna add a db table for it

add /health endpoint to API, Health API can reply with a "sweep_okay" bool
    this limits extra DB writes and doesn't create data that lies

Fourth sweeper logic pass:
wake
check /health for permission
run until complete:
    BEGIN IMMEDIATE
    SELECT oldest expired job LIMIT 1:
        if none:
            rollback and sleep
        otherwise:
            evaluate attempts for DLQ qualification:
                send to DLQ with error 
            otherwise:
                UPDATE jobs > set job_state to pending, set finished_at, worker_id, lease_initiated, lease_expiry, last_progress to NULL WHERE lease_expiry < ? AND attempt_number = ?
                UPDATE attempts > set outcome to lost, set error to lease-expired, ended_at to now
    COMMIT
sleep 10

/health 
GET endpoint
if now >= start_time + 60s 
    return 200 and "sweep_ok": [true]
else 
    return 200 and "sweep_ok": [false]