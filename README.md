# Mini Grid
A small compute grid modeled on portfolio analytics batching. A coordinator hands out Monte Carlo value-at-risk jobs to pull-based workers and survives worker failure. Built to familiarize myself with the intricacies of compute grids 

Status:
- [x] /claim
- [x] /heartbeat
- [x] /complete
- [x] /health
- [x] Sweep from running to pending
- [x] Sweep from running to dlq
- [x] /fail
- [x] Basic Worker process
- [x] Logging
- [x] Containerization
- [x] Ansible for deployment
- [ ] ELK stack setup
- [ ] Filebeat per VM
- [ ] Dashboards
- [ ] Full job trace
- [ ] ES internals refresh

Architecture:
DB - SQLite db containing jobs and attempts
Coordinator - API server for job manipulation
Sweeper - Process that requeues or disqualifies expired jobs. 
Worker - Pulls jobs from the table and works on them, and updates the database with a heartbeat and progress. 

Job Lifecycle:
Pending -> Claimed (Every claim creates a record in the attempts table. )
Claimed -> Running (A heartbeat moves the job from claimed to running. )
Running -> Complete (A worker completing the job moves the job from running to complete. )
Running/Claimed -> dlq (The sweeper moves jobs that exceed the attempt threshold to DLQ. )
Running -> Failed (A worker failing the job hits the failure endpoint. )
Failed -> pending (The sweeper will requeue a failed job. )

Failure Handling:
worker dies - Sweeper requeues job
worker slow - update transaction fails with incorrect attempt number
job kills worker - DLQ after 3 attempts with recorded error
coordinator restart - 60 second grace period for jobs to heartbeat
db unreachable - /health returns a 503 and sweeper stands down

To run from project root:

1. docker build -t minigrid .
2. docker compose up --scale worker=3
3. docker compose down


To reset the db:
1. docker compose down -v 

Known issues:
- [ ] SIGTERM for workers
- [ ] port 5000 lockdown

