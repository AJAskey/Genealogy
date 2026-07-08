"""
File: BuildDuckDBVaults.py

Summary: Replaces the old Python line-by-line vaulting process.
         Uses DuckDB to ingest the massive Census CSV, filter it, 
         and dynamically build the 'individuals' and 'families' 
         tables in a resume-friendly manner.
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
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

# --- CONFIGURATION ---
RAW_CENSUS_CSV = r"C:\tempc\ShortTermCSVfiles\census-1850-1950-ALL.csv"
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
TEMP_DIR = r"d:\Data\Genealogy_Data\duckdb_temp"


def main():
    logger = gen_logging.setup_logging('DuckDBVaultBuilder')
    logger.info("=====================================================================")
    logger.info("  TWO-STEP DUCKDB VAULT BUILDER (RESUME-FRIENDLY)")
    logger.info("=====================================================================")

    con = duckdb.connect(database=MASTER_VAULT_DB)
    start_time = time.time()

    # Enable DuckDB's built-in terminal progress bar for long-running queries!
    con.execute("PRAGMA enable_progress_bar;")

    # Create temp directory and force DuckDB to use D: drive for overflow to prevent C: drive crashes
    os.makedirs(TEMP_DIR, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{TEMP_DIR}';")
    con.execute("PRAGMA memory_limit='100GB';")
    
    # Check what tables already exist
    existing_tables = [r[0] for r in con.execute("SHOW TABLES;").fetchall()]

    # ---------------------------------------------------------
    # STEP 1: INGEST AND FILTER INDIVIDUALS
    # ---------------------------------------------------------
    if 'individuals' not in existing_tables:
        logger.info(f"STEP 1: Ingesting raw individuals from {RAW_CENSUS_CSV}...")
        # We apply the filters (like Race = White) right at the point of ingestion!
        con.execute(f"""
            CREATE TABLE individuals AS 
            SELECT * FROM read_csv('{RAW_CENSUS_CSV}', auto_detect=TRUE, all_varchar=TRUE)
            WHERE RACE = '1' AND SEX IS NOT NULL;
        """)
        logger.info("-> 'individuals' table created successfully.")
    else:
        logger.info("-> STEP 1: 'individuals' table already exists. Skipping ingestion.")

    # ---------------------------------------------------------
    # STEP 2: DYNAMICALLY BUILD FAMILIES
    # ---------------------------------------------------------
    if 'families' not in existing_tables:
        logger.info("STEP 2: Aggregating households to build the 'families' table...")
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
    else:
        logger.info("-> STEP 2: 'families' table already exists.")

    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"SUCCESS: Pipeline completed in {elapsed} minutes!")


if __name__ == '__main__':
    main()
