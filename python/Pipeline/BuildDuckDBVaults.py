"""
File: BuildDuckDBVaults.py

Summary: Replaces the old Python line-by-line vaulting process.
         Uses DuckDB to ingest the massive Census CSV, filter it, 
         and dynamically build the 'individuals' and 'families' 
         tables all in one blazing-fast step.
"""

import duckdb
import os
import sys
import time

# Dynamically add the project paths for utility imports
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(python_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils import gen_logging

# --- CONFIGURATION ---
RAW_CENSUS_CSV = r"C:\tempc\ShortTermCSVfiles\usa_00120.csv"
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"

def main():
    logger = gen_logging.setup_logging('DuckDBVaultBuilder')
    logger.info("=====================================================================")
    logger.info("  ONE-STEP DUCKDB VAULT BUILDER")
    logger.info("=====================================================================")

    if os.path.exists(MASTER_VAULT_DB):
        os.remove(MASTER_VAULT_DB)
        logger.info(f"Removed old database: {MASTER_VAULT_DB}")

    con = duckdb.connect(database=MASTER_VAULT_DB)
    start_time = time.time()

    # ---------------------------------------------------------
    # STEP 1: INGEST AND FILTER INDIVIDUALS
    # ---------------------------------------------------------
    logger.info(f"Ingesting raw individuals from {RAW_CENSUS_CSV}...")
    # We apply the filters (like Race = White) right at the point of ingestion!
    con.execute(f"""
        CREATE TABLE individuals AS 
        SELECT * FROM read_csv('{RAW_CENSUS_CSV}', auto_detect=TRUE, all_varchar=TRUE)
        WHERE RACE = '1' AND SEX IS NOT NULL;
    """)
    logger.info("-> 'individuals' table created successfully.")

    # ---------------------------------------------------------
    # STEP 2: DYNAMICALLY BUILD FAMILIES
    # ---------------------------------------------------------
    logger.info("Aggregating households to build the 'families' table...")
    # DuckDB groups by SERIAL (the household) and mathematically plucks out the Head,
    # the Spouse, and adds up the children's birth years on the fly.
    con.execute("""
        CREATE TABLE families AS
        SELECT 
            YEAR,
            SERIAL,
            MAX(CASE WHEN RELATE IN ('01', '1', 'Head/householder') THEN HISTID ELSE NULL END) AS head_histid,
            MAX(CASE WHEN RELATE IN ('02', '2', 'Spouse') THEN HISTID ELSE NULL END) AS spouse_histid,
            SUM(CASE WHEN RELATE IN ('03', '3', 'Child') THEN TRY_CAST(BIRTHYR AS INTEGER) ELSE 0 END) AS kids_byr_sum,
            COUNT(CASE WHEN RELATE IN ('03', '3', 'Child') THEN 1 ELSE NULL END) AS num_kids,
            STATEICP,
            COUNTYICP
        FROM individuals
        GROUP BY YEAR, SERIAL, STATEICP, COUNTYICP;
    """)
    logger.info("-> 'families' table created successfully.")

    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"SUCCESS: Vault successfully built in {elapsed} minutes!")

if __name__ == '__main__':
    main()