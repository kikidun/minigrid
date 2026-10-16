#! /bin/bash
rm ./grid.db
rm ./grid.db-shm
rm ./grid.db-wal
sqlite3 grid.db < schema.sql
sqlite3 grid.db < seed.sql