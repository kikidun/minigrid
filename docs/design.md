1. GOALS AND NON-GOALS
The goal of this project is to build a distributed compute grid performing Monte Carlo simulations on generated portfolios. No Kubernetes, no Swarm, no multiple coordinators, Just raw Linux, containers, python and a db.

Another goal of this project is to build observability for the compute grid on an infrastructure and application level. 

2. OVERVIEW
The distributed compute grid will be made up of the coordinator and workers on the same server to start with.

The coordinator will run three services. 
The scheduler which recieves and writes jobs, and picks up failed jobs for reassignment
The reconciler, which will reconcile the desired and available workers, the failed and healthy workers, and stuck/redundant jobs 
The failure detection service to check on the heartbeats of workers and mark workers as dead or stuck

Workers will run two services
Heartbeat - will ping the scheduler every 10 seconds to prove node liveness and also report job progress
Monty - will perform the actual simulation and report iteration #

DB

Observability
ELK or Grafana
Logs, and metrics

3. DATA MODEL
Tables:
Jobs
ID, state, worker_id, lease_timestamp, error, list_of_worker_attempts

Workers
ID, job_id, last_seen

4. STATE MACHINE
![alt text](image.png)

5. PROTOCOL
ask - request list of jobs 
claim - {"worker_id": id, "operation": claim, "job_id": job_id}
heartbeat - worker reaches out to coordinator with {"worker_id": id, "status": status, "progress": progress}
complete - worker reaches out to coordinator with {"worker_id": id, "job_id": job_id, "result": result}
fail - {"worker_id": id, "job_id": job_id, "error": error}
drop - {"job_id": job_id, "operation": drop}

6. FAILURE MODES
failure, detected, what happens
worker dies, no heartbeat for 45s, worker killed + attempts incremented + worker added to attempt list + job marked pending 
job hangs, no progress for 30s, job dropped + attempts incremented + worker added to attempt list + job marked pending
poison job, attempt count exceeded, job moved to DLQ
coordinator restart, not sure how to detect, heartbeat grace period + recover jobs?
db down, coordinator misses db heartbeat?, restart db?
network partition, not even sure how this would happen, 
sigterm, Recieved by python, graceful shutdown + mark job as failed/interrupted

7. DECISIONS

8. OPEN QUESTIONS
