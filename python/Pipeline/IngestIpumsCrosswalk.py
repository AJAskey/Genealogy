"""
File: IngestIpumsCrosswalk.py

Summary: Ingests the massive IPUMS linked data CSV (crosswalk) into a
         permanent, indexed DuckDB database for high-speed lookups.

"""

import duckdb
import os
import sys

# Dynamically add the project paths for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(python_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils import gen_logging

# --- CONFIGURATION ---
# Assumes the new 20GB CSV is in a path like this. Update if needed.
CROSSWALK_CSV_PATH = r"C:\tempc\ShortTermCSVfiles\mlp_census_crosswalk_v2_0.csv"
CROSSWALK_DB_PATH = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"


def main():
    """
    Reads the IPUMS crosswalk CSV and builds an indexed DuckDB database.
    """
    logger = gen_logging.setup_logging('IpumsCrosswalkIngester')
    logger.info("=====================================================================")
    logger.info("  IPUMS LINKED DATA CROSSWALK INGESTER")
    logger.info("=====================================================================")

    if not os.path.exists(CROSSWALK_CSV_PATH):
        logger.error(f"CRITICAL: IPUMS crosswalk CSV not found at: {CROSSWALK_CSV_PATH}")
        return

    if os.path.exists(CROSSWALK_DB_PATH):
        logger.warning(f"Database already exists at {CROSSWALK_DB_PATH}. Deleting old version.")
        os.remove(CROSSWALK_DB_PATH)

    logger.info(f"Creating new crosswalk database at: {CROSSWALK_DB_PATH}")
    con = duckdb.connect(database=CROSSWALK_DB_PATH)

    logger.info(f"Ingesting CSV from: {CROSSWALK_CSV_PATH}...")
    # Use DuckDB's highly optimized CSV reader to create and populate the table in one shot.
    con.execute(f"""
        CREATE TABLE ipums_crosswalk AS SELECT * FROM read_csv('{CROSSWALK_CSV_PATH}', auto_detect=TRUE, all_varchar=TRUE);
    """)
    logger.info("CSV ingestion complete. Table 'ipums_crosswalk' created.")

    # --- Build Indexes for Fast Lookups ---
    logger.info("Building indexes for fast lookups... (This may take a while)")

    # Get all column names from the newly created table, except the HIK which we'll do last
    columns = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'ipums_crosswalk'").fetchall()
    for col_tuple in columns:
        col = col_tuple[0]
        logger.info(f"  -> Indexing {col}...")
        con.execute(f"CREATE INDEX idx_{col.lower()} ON ipums_crosswalk({col});")

    logger.info("All indexes built successfully!")
    con.close()

    logger.info(f"SUCCESS: IPUMS Crosswalk database is ready for querying at {CROSSWALK_DB_PATH}")


if __name__ == '__main__':
    main()
