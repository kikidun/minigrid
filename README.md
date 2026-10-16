# Mini Grid
Build order:

A jobs table plus an HTTP claim endpoint with the atomic UPDATE ... WHERE state='pending'

A dumb worker: claim, sleep 5 in place of the real work, complete.

Heartbeats, then the dead-worker sweep. 

Then the child process and stall detection.