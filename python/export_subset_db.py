"""
-----------------------------------
File: export_subset_db.py

Summary: Creates a small, view-only SQLite database from the massive 
         Master Vault using a custom SQL filter. Since the Master Vault 
         already has all the IPUMS integer codes translated to text, 
         this script simply copies the filtered rows instantly.

Usage: Modify the TARGET_DB and SQL_FILTER variables, then run.
-----------------------------------
"""
import os

import duckdb

import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MASTER_100_DB = os.path.join(BASE_DATA_DIR, "MasterVault_ALL.db")
MASTER_SAMP_DB = os.path.join(BASE_DATA_DIR, "MasterVault_ALLs.db")
CLEAN_DB = os.path.join(BASE_DATA_DIR, "CleanVault.db")
TARGET_DB = os.path.join(BASE_DATA_DIR, "MasterVault_TEST.db")

# How many linked clusters (families/individuals) do you want in your test set?
SAMPLE_SIZE = 5000


def export_subset(logger):
    logger.info(f"Starting export to {os.path.basename(TARGET_DB)}...")

    # Connect to DuckDB in memory and set memory limits
    con = duckdb.connect(database=':memory:')
    con.execute("PRAGMA memory_limit='90GB';")

    # Load SQLite scanner
    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")

    # Attach the vaults (Read Only)
    logger.info("Attaching Master Vaults and Clean Vault...")
    con.execute(f"ATTACH '{MASTER_100_DB}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MASTER_SAMP_DB}' AS samp (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE, READ_ONLY);")

    # Delete the target DB if it already exists so we get a fresh copy
    if os.path.exists(TARGET_DB):
        os.remove(TARGET_DB)

    # Attach the brand new target SQLite database
    logger.info(f"Creating Target DB: {TARGET_DB}")
    con.execute(f"ATTACH '{TARGET_DB}' AS target (TYPE SQLITE);")

    logger.info(f"Executing transfer... pulling {SAMPLE_SIZE:,} known linked clusters.")
    
    con.execute(f"""
        -- 1. Create the empty table structure
        CREATE TABLE target.population AS 
        SELECT * FROM base.population WHERE 1=0;

        -- 2. Pick {SAMPLE_SIZE} Golden Records that actually have cross-decade matches (record_count > 1)
        CREATE TEMP TABLE sampled_clusters AS
        SELECT * FROM (
            SELECT vault_pointers 
            FROM clean.golden_records 
            WHERE record_count > 1
        ) USING SAMPLE {SAMPLE_SIZE} ROWS;

        -- 3. Unnest the pipe-delimited pointers to get the exact composite_ids
        CREATE TEMP TABLE sampled_ids AS
        SELECT DISTINCT UNNEST(string_split(vault_pointers, '|')) AS comp_id
        FROM sampled_clusters;

        -- 4. Copy those EXACT original rows from the raw vaults into the test database
        INSERT INTO target.population
        SELECT * FROM base.population WHERE composite_id IN (SELECT comp_id FROM sampled_ids)
        UNION 
        SELECT * FROM samp.population WHERE composite_id IN (SELECT comp_id FROM sampled_ids);
    """)

    # Get the final count
    count = con.execute("SELECT COUNT(*) FROM target.population").fetchone()[0]

    logger.info(f"Success! {count:,} records were written to {os.path.basename(TARGET_DB)}.")
    logger.info("You can now open this smaller database in DB Browser.")

    con.close()


if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="SUBSET")
    export_subset(logger)
