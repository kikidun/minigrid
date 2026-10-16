#! /bin/bash
rm -f ./grid.db
rm -f ./grid.db-shm
rm -f ./grid.db-wal
sqlite3 grid.db < schema.sql
sqlite3 grid.db < seed.sql