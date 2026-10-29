import sqlite3
import config
import os
import jsonlog
import logging

SQL_DIR = config.BASE_DIR.parent / "db"

if __name__ == "__main__":
    jsonlog.setup("db-init")
    existed = os.path.exists(config.DB_PATH)

    con = config.connect()
    con.executescript((SQL_DIR / "schema.sql").read_text())
    if existed:
        logging.info("db already initialized at %s, skipping seed", config.DB_PATH)
    else:
        con.executescript((SQL_DIR / "seed.sql").read_text())
        logging.info("new db at %s, schema created and seeded", config.DB_PATH)
    con.close()