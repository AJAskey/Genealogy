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

import argparse
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
GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"
SPLINK_MODEL_JSON = r"D:\Data\Genealogy_Data\splink_model.json"

def run_analyst_pipeline(logger, mode="link", is_test=False):
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

    if is_test:
        logger.info("*** RUNNING IN TEST MODE ***")
        db_100 = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
        db_samples = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
        db_clean = r"D:\Data\Genealogy_Data\CleanVault_TEST.db"
    else:
        db_100 = CENSUS_100_DB
        db_samples = CENSUS_SAMPLES_DB
        db_clean = CLEAN_DB

    # Attach the dual databases directly from the NVMe drive
    logger.info(f"Attaching 100% Census Base Vault: {db_100}")
    con.execute(f"ATTACH '{db_100}' AS census100 (TYPE SQLITE);")

    logger.info(f"Attaching Census Samples Patch Vault: {db_samples}")
    con.execute(f"ATTACH '{db_samples}' AS samples (TYPE SQLITE);")

    logger.info(f"Attaching Death Index Vault: {BIRLS_DB}")
    con.execute(f"ATTACH '{BIRLS_DB}' AS birls (TYPE SQLITE);")

    logger.info(f"Attaching Clean Vault: {db_clean}")
    con.execute(f"ATTACH '{db_clean}' AS clean (TYPE SQLITE);")

    logger.info(f"Attaching Gedcom Vault: {GEDCOM_DB}")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE);")

    # Safety check: Create the table if it doesn't exist yet so the pipeline doesn't crash
    con.execute("""
        CREATE TABLE IF NOT EXISTS gedcom.gedcom_records (
            gedcom_id TEXT PRIMARY KEY,
            full_name VARCHAR,
            first_name VARCHAR,
            last_name VARCHAR,
            birth_date VARCHAR,
            birth_year INTEGER,
            birth_place VARCHAR,
            death_date VARCHAR,
            death_place VARCHAR,
            picture_url VARCHAR
        );
    """)

    logger.info("All vaults successfully attached! Engine is primed.")

    # ---------------------------------------------------------
    # PHASE 1: PREPARE DATA FOR SPLINK (RENAMING & FILTERING)
    # ---------------------------------------------------------
    logger.info("Extracting ALL nationwide records and normalizing columns for Splink...")

    # Create a temporary table of names from the target state to pre-filter the massive BIRLS death index.
    # This prevents joining ALL 15M+ death records against a single state.
    logger.info("Pre-filtering death index for relevant names...")
    con.execute(f"""
        CREATE TEMP TABLE target_names AS
        SELECT DISTINCT namelast FROM census100.population WHERE namelast IS NOT NULL AND REGEXP_MATCHES(namelast, '[a-zA-Z]')
        UNION
        SELECT DISTINCT namelast FROM samples.population WHERE namelast IS NOT NULL AND REGEXP_MATCHES(namelast, '[a-zA-Z]');
    """)

    # We build an in-memory table that maps IPUMS variables to Splink standard names
    con.execute(f"""
        CREATE TABLE population_master AS
                                                                                 WITH base_filtered AS (
            -- Push filter down to SQLite before bringing into DuckDB
            SELECT * FROM census100.population
        ),
        samp_filtered AS (
            -- Pre-filter the samples DB and apply 'The Squash' logic to prevent Cartesian explosion
            SELECT year, serial, pernum, 
                   MAX(namefrst) as namefrst, 
                   MAX(namelast) as namelast,
                   MAX(birthyr) as birthyr,
                   MAX(sex) as sex,
                   MAX(bpld) as bpld,
                   MAX(stateicp) as stateicp
            FROM samples.population 
            GROUP BY year, serial, pernum
        ),
        collapsed_census AS (
            SELECT 
                base.composite_id AS unique_id,
                COALESCE(samp.namefrst, base.namefrst) AS first_name,
                COALESCE(samp.namelast, base.namelast) AS last_name,
                NULLIF(CAST(COALESCE(samp.birthyr, base.birthyr) AS INTEGER), 9999) AS birth_year,
                COALESCE(samp.stateicp, base.stateicp) AS state,
                COALESCE(samp.sex, base.sex) AS sex,
                COALESCE(samp.bpld, base.bpld) AS birth_place,
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
        WHERE last_name IS NOT NULL AND REGEXP_MATCHES(last_name, '[a-zA-Z]')
          AND first_name IS NOT NULL AND REGEXP_MATCHES(first_name, '[a-zA-Z]')
        UNION ALL
        SELECT 
            'DEATH_' || CAST(record_id AS VARCHAR) AS unique_id,
            first AS first_name,
            last AS last_name,
            TRY_CAST(SUBSTR(dob, 1, 4) AS INTEGER) AS birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS VARCHAR) AS sex,
            CAST(NULL AS VARCHAR) AS birth_place,
            CAST(NULL AS INTEGER) AS census_year,
            dod AS death_date,
            'death_index' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM birls.birls_records
        WHERE last IN (SELECT namelast FROM target_names)
          AND last IS NOT NULL AND REGEXP_MATCHES(last, '[a-zA-Z]')
          AND first IS NOT NULL AND REGEXP_MATCHES(first, '[a-zA-Z]')
        UNION ALL
        SELECT 
            'GED_' || gedcom_id AS unique_id,
            first_name,
            last_name,
            birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS VARCHAR) AS sex,
            birth_place,
            CAST(NULL AS INTEGER) AS census_year,
            death_date,
            'gedcom' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM gedcom.gedcom_records
        WHERE last_name IS NOT NULL AND REGEXP_MATCHES(last_name, '[a-zA-Z]')
          AND first_name IS NOT NULL AND REGEXP_MATCHES(first_name, '[a-zA-Z]')
    """)

    row_count = con.execute("SELECT COUNT(*) FROM population_master").fetchone()[0]
    logger.info(f"Successfully extracted {row_count:,} records nationwide.")

    # ---------------------------------------------------------
    # PHASE 2: GOLDEN RECORD GENERATION (SPLINK)
    # ---------------------------------------------------------
    logger.info("Initializing Splink Linker...")
    import string
    
    if mode in ("train", "both"):
        logger.info("Setting up view for TRAINING (using full dataset)...")
        con.execute("CREATE OR REPLACE VIEW population_for_splink AS SELECT * FROM population_master;")
        generator = CreateGoldenRecord(db_connection=con, logger=logger)
        generator.run(mode="train", output_table="clean.golden_records", model_path=SPLINK_MODEL_JSON)
        if mode == "train":
            return
            
    if mode in ("link", "both"):
        slices = list(string.ascii_uppercase) + ["OTHER"]
        
        # Auto-Resume Logic: Find which letters are already finished in the Clean Vault
        try:
            completed_letters = [r[0] for r in con.execute("SELECT DISTINCT UPPER(SUBSTR(last_name, 1, 1)) FROM clean.golden_records").fetchall()]
        except Exception:
            completed_letters = []

        for letter in slices:
            if letter in completed_letters:
                logger.info(f"*** Slice '{letter}' already exists in Clean Vault. Skipping! (Auto-Resume) ***")
                continue

            logger.info(f"\n{'='*60}\n--- Slicing Data: Last Names starting with '{letter}' ---\n{'='*60}")
            
            if letter == "OTHER":
                # Catch names starting with numbers, quotes, or special characters
                letters_list = "', '".join(list(string.ascii_uppercase))
                condition = f"UPPER(SUBSTR(last_name, 1, 1)) NOT IN ('{letters_list}')"
            else:
                condition = f"UPPER(SUBSTR(last_name, 1, 1)) = '{letter}'"
                
            con.execute(f"CREATE OR REPLACE VIEW population_for_splink AS SELECT * FROM population_master WHERE {condition};")
            
            slice_count = con.execute("SELECT COUNT(*) FROM population_for_splink").fetchone()[0]
            if slice_count == 0:
                logger.info(f"  -> No records found for '{letter}'. Skipping.")
                continue
                
            logger.info(f"  -> Processing {slice_count:,} records for slice '{letter}'...")
            generator = CreateGoldenRecord(db_connection=con, logger=logger)
            generator.run(mode="link", output_table="clean.golden_records", model_path=SPLINK_MODEL_JSON)
            
        logger.info("\nAll alphabetical slices completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Phase 2 Analyst Pipeline.")
    parser.add_argument("--mode", choices=["train", "link", "both"], default="link",
                        help="Pipeline mode: 'train' (train AI only), 'link' (cluster using saved model), or 'both'.")
    parser.add_argument("--test", action="store_true",
                        help="Run against MasterVault_TEST.db and output to CleanVault_TEST.db")
    args = parser.parse_args()

    main_logger = gen_logging.setup_logging(logger_name="ANALYST")
    run_analyst_pipeline(main_logger, mode=args.mode, is_test=args.test)