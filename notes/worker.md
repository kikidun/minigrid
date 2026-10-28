Loop:
1. Get a job
2. If no jobs, wait and goto 1
3. If job, run it. Send heartbeats every 10s
4. When it finishes, report complete and goto 1

A Python process is a whole Python program with its own memory. Receives data through pipes or queues. Lives in the multiprocessing module.

A Python thread is a second path of execution inside the same Python program, sharing all of the same variables and memory. Lives in the `threading` module 

C Python lets one thread run Python code at any instant, and threads take turns every 5 ms by default. 

Threading does not make CPU work faster. 

The heartbeat thread is almost always waiting, so we can use a heartbeat thread next to a job, even if the job is CPU-heavy, due to the 5 ms turns. 

You cannot kill a Python thread, so the heartbeat cannot kill the job if it finds out it's out of date. The heartbeat will need to set a flag that the job checks before working. "cooperative cancellation"

However, a child process can be killed from outside, so it's possible the worker does the computation as a child process. 

threading.Event is how the threads will talk. 
lease_lost: set by heartbeat when it gets a 409 response. Job checks this flag between steps and stops.
job_done: set by the main thread when the job finishes. 

Loop with Events:
1. Get a job
    1a. create both events
    1b. start heartbeat
    1c. start job
2. If no jobs, wait and goto 1
3. If job, run it. Send heartbeats every 10s
    3a. run step
    3b. check lease_lost, bail if true
    3c. heartbeat wait up to 10s on job_done
        if set, exit
        otherwise send heartbeat
        on 409, set lease_lost and exit
4. When it finishes
    4a. main thread set job_done
    4b. call join on heartbeat thread
    4c. if lease_lost, log and throw away result
    4d. otherwise call /complete