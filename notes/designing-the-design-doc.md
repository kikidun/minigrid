put the design document together based off the following list

1. GOALS AND NON-GOALS

2. OVERVIEW

3. DATA MODEL

4. STATE MACHINE

5. PROTOCOL

6. FAILURE MODES

7. DECISIONS

8. OPEN QUESTIONS

After my first pass, I realize I missed zombie workers entirely and need to address idempotency. 
    jobs need to carry an attempt number, claim and heartbeat need it. 
    reject write when job is done
I am also not sure what the "scheduler" actually has to do or if it's necessary if the workers are pulling jobs. 
Attempt count logic
What happens to a job that doesn't start?
attempts table
lease logic

get rid of ask
add job to heartbeat
think about drop
transport?

second pass:
zombie detection via stale result
reject any job that comes in with a different attempt number
network partition idk if i want to do right now, actrually just zombie

claim job should split into request and response
claim request with worker_id, respond with job_id, attempt

startup = grace period + claimed and running

where does a result live if cant be committed? 
who holds onto it and retries? coordinator?
why is retried complete safe to apply twice?
