PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    job_state TEXT NOT NULL DEFAULT 'pending' CHECK (job_state IN ('pending','claimed','running','complete','failed','dlq')),
    worker_id TEXT,
    created_at INTEGER NOT NULL,
    lease_initiated INTEGER,
    lease_expiry INTEGER,
    last_progress INTEGER,
    finished_at INTEGER,
    error TEXT,
    attempt_number INTEGER NOT NULL DEFAULT 0,
    params TEXT NOT NULL,
    result TEXT,

    --- checks to make sure job_state is valid
    CHECK (job_state != 'pending'
           OR (worker_id IS NULL AND lease_initiated IS NULL AND finished_at IS NULL)),
    -- claimed or running: someone owns it and holds a lease
    CHECK (job_state NOT IN ('claimed','running')
           OR (worker_id IS NOT NULL AND lease_initiated IS NOT NULL AND lease_expiry IS NOT NULL)),
    -- complete: it finished, and there's no error
    CHECK (job_state != 'complete'
           OR (finished_at IS NOT NULL AND error IS NULL)),
    -- failed or dlq: there must be a reason
    CHECK (job_state NOT IN ('failed','dlq') OR error IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    attempt_number INTEGER NOT NULL,
    worker_id TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    outcome TEXT,
    error TEXT,

    CHECK (outcome IN ('running','succeeded','failed','stalled','died'))
);

-- Workers only ever scan for claimable jobs;
CREATE INDEX IF NOT EXISTS jobs_claimable ON jobs (created_at) WHERE job_state = 'pending';


