"""
-----------------------------------
File: run_analyst.py

Summary: The Driver script for Phase 2. Uses DuckDB to attach the 
         Census Master Vault, the Death Index Vault, and the Clean Vault
         simultaneously. This allows lightning-fast cross-database joins 
         without loading them into memory.

Design:
  - Mounts SQLite databases using DuckDB's native SQLite scanner.
  - Executes a test join to prove cross-vault visibility.
  - Serves as the launchpad for GoldenRecordGenerator & Splink.
-----------------------------------
"""

import time
import os
import duckdb
import gen_logging
from CreateGoldenRecord import CreateGoldenRecord

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CENSUS_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
CENSUS_SAMPLES_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
BIRLS_DB = r"D:\Data\Genealogy_Data\DeathIndexVault.db"
CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
SPLINK_MODEL_JSON = r"D:\Data\Genealogy_Data\splink_model.json"

# Claude's Safety Filter: Only process one state until the logic is proven!
STATE_FILTER = "Alabama"

def run_analyst_pipeline(logger):
    logger.info("Initializing DuckDB In-Memory Engine...")
    con = duckdb.connect(database=':memory:')
    
    # Set memory limits to prevent 100% RAM usage crashes during massive runs, 
    # forcing overflow to your lightning-fast NVMe drive instead.
    logger.info("Configuring DuckDB memory safety limits...")
    con.execute("PRAGMA memory_limit='90GB';")
    temp_dir = r"D:\Data\Genealogy_Data\DuckDB_Temp"
    os.makedirs(temp_dir, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{temp_dir}';")

    # Install and load the SQLite extension for DuckDB
    logger.info("Loading SQLite scanner extension...")
    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")

    # Attach the dual databases directly from the NVMe drive
    logger.info(f"Attaching 100% Census Base Vault: {CENSUS_100_DB}")
    con.execute(f"ATTACH '{CENSUS_100_DB}' AS census100 (TYPE SQLITE);")

    logger.info(f"Attaching Census Samples Patch Vault: {CENSUS_SAMPLES_DB}")
    con.execute(f"ATTACH '{CENSUS_SAMPLES_DB}' AS samples (TYPE SQLITE);")

    logger.info(f"Attaching Death Index Vault: {BIRLS_DB}")
    con.execute(f"ATTACH '{BIRLS_DB}' AS birls (TYPE SQLITE);")

    logger.info(f"Attaching Clean Vault: {CLEAN_DB}")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE);")

    logger.info("All vaults successfully attached! Engine is primed.")

    # ---------------------------------------------------------
    # PHASE 1: PREPARE DATA FOR SPLINK (RENAMING & FILTERING)
    # ---------------------------------------------------------
    logger.info(f"Extracting '{STATE_FILTER}' records and normalizing columns for Splink...")

    # Create a temporary table of names from the target state to pre-filter the massive BIRLS death index.
    # This prevents joining ALL 15M+ death records against a single state.
    logger.info("Pre-filtering death index for relevant names...")
    con.execute(f"""
        CREATE TEMP TABLE target_names AS
        SELECT DISTINCT namelast FROM census100.population WHERE stateicp = '{STATE_FILTER}' AND namelast IS NOT NULL
        UNION
        SELECT DISTINCT namelast FROM samples.population WHERE stateicp = '{STATE_FILTER}' AND namelast IS NOT NULL;
    """)

    # We build an in-memory table that maps IPUMS variables to Splink standard names
    con.execute(f"""
        CREATE TABLE population_for_splink AS
                                                                                 WITH base_filtered AS (
            -- Push filter down to SQLite before bringing into DuckDB
            SELECT * FROM census100.population 
            WHERE stateicp = '{STATE_FILTER}'
        ),
        samp_filtered AS (
            -- Pre-filter the samples DB and apply 'The Squash' logic to prevent Cartesian explosion
            SELECT year, serial, pernum, 
                   MAX(namefrst) as namefrst, 
                   MAX(namelast) as namelast,
                   MAX(birthyr) as birthyr,
                   MAX(stateicp) as stateicp
            FROM samples.population 
            WHERE stateicp = '{STATE_FILTER}'
            GROUP BY year, serial, pernum
        ),
        collapsed_census AS (
            SELECT 
                base.composite_id AS unique_id,
                COALESCE(samp.namefrst, base.namefrst) AS first_name,
                COALESCE(samp.namelast, base.namelast) AS last_name,
                CAST(COALESCE(samp.birthyr, base.birthyr) AS INTEGER) AS birth_year,
                COALESCE(samp.stateicp, base.stateicp) AS state,
                CAST(base.year AS INTEGER) AS census_year,
                CAST(NULL AS VARCHAR) AS death_date,
                'census' AS source_db,
                -- Build Father ID pointer: sample_serial_poploc
                CASE WHEN TRY_CAST(base.poploc AS INTEGER) > 0 
                     THEN SPLIT_PART(base.composite_id, '_', 1) || '_' || SPLIT_PART(base.composite_id, '_', 2) || '_' || base.poploc 
                     ELSE NULL END AS father_pointer,
                -- Build Mother ID pointer: sample_serial_momloc
                CASE WHEN TRY_CAST(base.momloc AS INTEGER) > 0 
                     THEN SPLIT_PART(base.composite_id, '_', 1) || '_' || SPLIT_PART(base.composite_id, '_', 2) || '_' || base.momloc 
                     ELSE NULL END AS mother_pointer
            FROM base_filtered base
            LEFT JOIN samp_filtered samp
              ON base.year = samp.year AND base.serial = samp.serial AND base.pernum = samp.pernum
        )
        SELECT * FROM collapsed_census
        WHERE last_name IS NOT NULL 
          AND first_name IS NOT NULL
        UNION ALL
        SELECT 
            'BIRLS_' || CAST(record_id AS VARCHAR) AS unique_id,
            first AS first_name,
            last AS last_name,
            TRY_CAST(SUBSTR(dob, 1, 4) AS INTEGER) AS birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS INTEGER) AS census_year,
            dod AS death_date,
            'birls' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM birls.birls_records
        WHERE last IN (SELECT namelast FROM target_names)
          AND last IS NOT NULL 
          AND first IS NOT NULL
    """)

    row_count = con.execute("SELECT COUNT(*) FROM population_for_splink").fetchone()[0]
    logger.info(f"Successfully extracted {row_count:,} records for {STATE_FILTER}.")

    # ---------------------------------------------------------
    # PHASE 2: GOLDEN RECORD GENERATION (SPLINK)
    # ---------------------------------------------------------
    logger.info("Initializing Splink Linker...")
    generator = CreateGoldenRecord(db_connection=con, logger=logger)
    generator.run(output_table="clean.golden_records", model_path=SPLINK_MODEL_JSON)


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="ANALYST")
    run_analyst_pipeline(main_logger)