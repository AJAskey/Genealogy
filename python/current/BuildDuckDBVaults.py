"""
File: BuildDuckDBVaults.py

Summary: Replaces the old Python line-by-line vaulting process.
         Uses DuckDB to ingest the massive Census CSV, filter it, 
         and dynamically build the 'individuals' and 'families' 
         tables in a resume-friendly manner.
"""

import os
import sys
import time

import duckdb

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
RAW_CENSUS_CSV = r"C:\tempc\ShortTermCSVfiles\super_trackers_pa.csv"
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\NewHIK_DuckDB_Vault.db"
# RAW_CENSUS_CSV = r"C:\tempc\ShortTermCSVfiles\census_samples.csv"
# MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Sample_DuckDB_Vault.db"
TEMP_DIR = r"d:\Data\Genealogy_Data\duckdb_temp"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"


def main():
    logger = gen_logging.setup_logging('DuckTestDBVaultBuilder')
    logger.info("=====================================================================")
    logger.info("  TWO-STEP DUCKDB VAULT BUILDER (RESUME-FRIENDLY)")
    logger.info("=====================================================================")

    con = duckdb.connect(database=MASTER_VAULT_DB)
    start_time = time.time()

    # 1. Force DuckDB to use every single hardware thread your processor has
    con.execute("PRAGMA threads=24;")

    # 2. BREAK THE BOTTLENECK: Tell DuckDB not to wait in line.
    con.execute("PRAGMA preserve_insertion_order=FALSE;")

    # Enable DuckDB's built-in terminal progress bar for long-running queries!
    con.execute("PRAGMA enable_progress_bar;")

    # Create temp directory and force DuckDB to use D: drive for overflow to prevent C: drive crashes
    os.makedirs(TEMP_DIR, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{TEMP_DIR}';")

    # 3. Raise the memory ceiling slightly since you have 128GB
    con.execute("PRAGMA memory_limit='110GB';")

    # Check what tables already exist
    existing_tables = [r[0] for r in con.execute("SHOW TABLES;").fetchall()]

    # ---------------------------------------------------------
    # STEP 1: INGEST AND FILTER INDIVIDUALS
    # ---------------------------------------------------------
    if 'individuals' not in existing_tables:
        logger.info(f"STEP 1: Ingesting raw individuals from {RAW_CENSUS_CSV}...")
        logger.info(f"STEP 1:                           to {MASTER_VAULT_DB}...")

        # Dynamically check if HISTID exists in the CSV
        headers = [col[0].upper() for col in con.execute(
            f"SELECT * FROM read_csv('{RAW_CENSUS_CSV}', auto_detect=TRUE, all_varchar=TRUE) LIMIT 0").description]

        if 'HISTID' in headers:
            select_clause = "*"
        else:
            logger.info("-> 'HISTID' not found in CSV. Synthesizing ID from YEAR_SERIAL_PERNUM...")
            select_clause = "*, YEAR || '_' || SERIAL || '_' || PERNUM AS HISTID"

        # Attach and unpivot the Crosswalk right before ingestion
        logger.info("-> Attaching Crosswalk database...")
        con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

        logger.info("-> Unpivoting Crosswalk data into memory (this takes a moment)...")
        con.execute("""
                    CREATE
                    TEMP TABLE cw_unpivoted AS
                    SELECT TRIM(histid_1850) AS histid, HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1850)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1860), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1860)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1870), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1870)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1880), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1880)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1900), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1900)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1910), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1910)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1920), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1920)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1930), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1930)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1940), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1940)) > 5
                    UNION ALL
                    SELECT TRIM(histid_1950), HIK
                    FROM cw.ipums_crosswalk
                    WHERE LENGTH(TRIM(histid_1950)) > 5;
                    """)

        # Apply the filters AND merge the HIK right at the point of ingestion!
        logger.info("-> Creating 'individuals' table and permanently joining the HIK...")
        con.execute(f"""
            CREATE TABLE individuals AS 
            WITH raw_csv AS (
                SELECT {select_clause} 
                FROM read_csv('{RAW_CENSUS_CSV}', auto_detect=TRUE, all_varchar=TRUE, ignore_errors=TRUE)
                WHERE RACE = '1' AND SEX IS NOT NULL
            )
            SELECT r.*, COALESCE(c.HIK, r.HISTID) AS HIK
            FROM raw_csv r
            LEFT JOIN cw_unpivoted c ON UPPER(TRIM(r.HISTID)) = UPPER(c.histid);
        """)
        logger.info("-> 'individuals' table created successfully with native HIKs.")
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
                        MAX
                    (
                        CASE
                        WHEN
                        RELATE
                        IN
                    (
                        '01',
                        '1',
                        'Head/householder'
                    ) THEN HISTID ELSE NULL END) AS head_histid,
                        MAX
                    (
                        CASE
                        WHEN
                        RELATE
                        IN
                    (
                        '02',
                        '2',
                        'Spouse'
                    ) THEN HISTID ELSE NULL END) AS spouse_histid,
                        SUM
                    (
                        CASE
                        WHEN
                        RELATE
                        IN
                    (
                        '03',
                        '3',
                        'Child'
                    ) THEN TRY_CAST
                    (
                        BIRTHYR AS
                        INTEGER
                    ) ELSE 0 END) AS kids_byr_sum,
                        COUNT
                    (
                        CASE
                        WHEN
                        RELATE
                        IN
                    (
                        '03',
                        '3',
                        'Child'
                    ) THEN 1 ELSE NULL END) AS num_kids,
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
