instaklled sqlite

need a script to set up the tables, maybe can clear them too

ID, state, worker_id, lease_initiation_timestamp, last_progress_timestamp, error, attempt_count, attempt_id

Going to start with the Python script to set up and configure the database. Need to review parameterization. 

starting with:
        id INTEGER PRIMARY KEY,
        job_state TEXT,
        worker_id TEXT UNIQUE,
        lease_initiated INTEGER,
        last_progress INTEGER,
        error TEXT,
        attempt_count INTEGER,
        attempt_id INTEGER UNIQUE

Adding check statements, 

"CHECK (job_state != 'running' OR worker_id IS NOT NULL)" - If the job is running, it must have a worker. For any job that isn't running, the left side of the statement is true. For any job that is running, the right side of the statement must be true. 

current schema:
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    job_state TEXT NOT NULL DEFAULT 'pending' CHECK (job_state IN ('pending','claimed','running','complete','failed','dlq')),
    worker_id TEXT UNIQUE,
    lease_initiated INTEGER,
    last_progress INTEGER,
    finished_at INTEGER,
    error TEXT,
    attempt_number INTEGER NOT NULL DEFAULT 0,
    attempt_id INTEGER UNIQUE

    --- checks to make sure job_state is valid
    CHECK (job_state != 'pending'
           OR (worker_id IS NULL AND lease_started IS NULL AND finished_at IS NULL)),
    -- claimed or running: someone owns it and holds a lease
    CHECK (job_state NOT IN ('claimed','running')
           OR (worker_id IS NOT NULL AND lease_started IS NOT NULL AND lease_expires IS NOT NULL)),
    -- complete: it finished, and there's no error
    CHECK (job_state != 'complete'
           OR (finished_at IS NOT NULL AND error IS NULL)),
    -- failed or dlq: there must be a reason
    CHECK (job_state NOT IN ('failed','dlq') OR error IS NOT NULL)
) STRICT;


While designing the claim endpoint, I realized the database currently isn't storing the actual job payload or the job results, so those have been added to the schema. 
The claim will also be atomic, where the database finds A job for a claiming worker assigns the job and then replies with the job. 

pulled attempt_id out of the jobs table

attempts table:


CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    job_id INTEGER FOREIGN KEY REFERENCES jobs(id),
    attempt_number INTEGER NOT NULL,
    worker_id TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    outcome TEXT,
    error TEXT,

    CHECK (outcome IN ('running','succeeded','failed','stalled','died'))
)

