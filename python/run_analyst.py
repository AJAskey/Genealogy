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
import os
import sys
import string
import sqlite3
import pandas as pd

import duckdb

# Ensure we can import from the utils directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
if script_dir not in sys.path:
    sys.path.append(script_dir)

from CreateGoldenRecord import CreateGoldenRecord
from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CENSUS_100_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
CENSUS_SAMPLES_DB = r"D:\Data\Genealogy_Data\MasterVault_ALLs.db"
BIRLS_DB = r"D:\Data\Genealogy_Data\DeathIndexVault.db"
CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
CLEAN_TRACER_DB = r"D:\Data\Genealogy_Data\CleanVault_Gedcom.db"
GEDCOM_DB = r"D:\Data\Genealogy_Data\GedcomVault.db"
SPLINK_MODEL_JSON = r"D:\Data\Genealogy_Data\splink_model.json"

# Point this to whatever drive has the MOST free space (e.g., hundreds of GBs)
DUCKDB_TEMP_DIR = r"D:\Data\Genealogy_Data\DuckDB_Temp"


def run_analyst_pipeline(logger, mode="link", is_test=False, is_tracer=False):
    logger.info("Initializing DuckDB In-Memory Engine...")
    con = duckdb.connect(database=':memory:')

    # Set memory limits to prevent 100% RAM usage crashes during massive runs, 
    # forcing overflow to your lightning-fast NVMe drive instead.
    logger.info("Configuring DuckDB memory safety limits...")
    con.execute("PRAGMA memory_limit='90GB';")
    os.makedirs(DUCKDB_TEMP_DIR, exist_ok=True)
    con.execute(f"PRAGMA temp_directory='{DUCKDB_TEMP_DIR}';")

    # Install and load the SQLite extension for DuckDB
    logger.info("Loading SQLite scanner extension...")
    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")

    if is_test:
        logger.info("*** RUNNING IN TEST MODE ***")
        db_100 = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
        db_samples = r"D:\Data\Genealogy_Data\MasterVault_TEST.db"
        db_clean = r"D:\Data\Genealogy_Data\CleanVault_TEST.db"
    elif is_tracer:
        logger.info("*** RUNNING IN TRACER MODE ***")
        db_100 = CENSUS_100_DB
        db_samples = CENSUS_SAMPLES_DB
        db_clean = CLEAN_TRACER_DB
    else:
        db_100 = CENSUS_100_DB
        db_samples = CENSUS_SAMPLES_DB
        db_clean = CLEAN_DB

    # Attach the dual databases directly from the NVMe drive
    logger.info(f"Attaching 100% Census Base Vault: {db_100}")
    con.execute(f"ATTACH '{db_100}' AS census100 (TYPE SQLITE, READ_ONLY);")

    logger.info(f"Attaching Census Samples Patch Vault: {db_samples}")
    con.execute(f"ATTACH '{db_samples}' AS samples (TYPE SQLITE, READ_ONLY);")

    logger.info(f"Attaching Death Index Vault: {BIRLS_DB}")
    con.execute(f"ATTACH '{BIRLS_DB}' AS birls (TYPE SQLITE, READ_ONLY);")

    logger.info(f"Attaching Clean Vault: {db_clean}")
    con.execute(f"ATTACH '{db_clean}' AS clean (TYPE SQLITE);")

    logger.info(f"Attaching Gedcom Vault: {GEDCOM_DB}")
    con.execute(f"ATTACH '{GEDCOM_DB}' AS gedcom (TYPE SQLITE, READ_ONLY);")

    logger.info("All vaults successfully attached! Engine is primed.")

    # ---------------------------------------------------------
    # PHASE 1: PREPARE DATA FOR SPLINK (RENAMING & FILTERING)
    # ---------------------------------------------------------
    if is_tracer:
        logger.info("TRACER BULLET MODE: Extracting target surnames from GedcomVault...")
        # Get target names into a Python list so we can inject them as an IN clause!
        # This allows DuckDB to push the filter down into the SQLite scanner natively, using SQLite's B-Tree indexes!
        target_names_df = con.execute("SELECT DISTINCT last_name FROM gedcom.gedcom_records WHERE last_name IS NOT NULL AND REGEXP_MATCHES(last_name, '[a-zA-Z]')").df()
        
        name_list = []
        for name in target_names_df.iloc[:, 0].tolist():
            name = str(name).strip()
            name_list.append(name.upper())
            name_list.append(name.capitalize())
            name_list.append(name.lower())
            
        in_clause = ", ".join([f"'{n.replace(chr(39), chr(39)+chr(39))}'" for n in set(name_list)])
        
        name_filter_base = f"b.namelast IN ({in_clause})"
        name_filter_samp = f"s.namelast IN ({in_clause})"
        name_filter_birls = f"b_r.last IN ({in_clause}) AND b_r.last IS NOT NULL AND REGEXP_MATCHES(b_r.last, '[a-zA-Z]')"
        name_filter_uni = f"u_d.last_name IN ({in_clause}) AND u_d.last_name IS NOT NULL AND REGEXP_MATCHES(u_d.last_name, '[a-zA-Z]')"
        name_filter_gedcom = f"g_r.last_name IN ({in_clause}) AND g_r.last_name IS NOT NULL AND REGEXP_MATCHES(g_r.last_name, '[a-zA-Z]')"
        
        names_count = len(target_names_df)
    else:
        logger.info("NATIONWIDE MODE: Processing ALL valid records...")
        # In nationwide mode, we process everything. No need to join against a massive target_names table.
        # This removes the combinatorial join explosion completely.
        name_filter_base = "b.namelast IS NOT NULL AND REGEXP_MATCHES(b.namelast, '[a-zA-Z]')"
        name_filter_samp = "s.namelast IS NOT NULL AND REGEXP_MATCHES(s.namelast, '[a-zA-Z]')"
        name_filter_birls = "b_r.last IS NOT NULL AND REGEXP_MATCHES(b_r.last, '[a-zA-Z]')"
        name_filter_uni = "u_d.last_name IS NOT NULL AND REGEXP_MATCHES(u_d.last_name, '[a-zA-Z]')"
        name_filter_gedcom = "g_r.last_name IS NOT NULL AND REGEXP_MATCHES(g_r.last_name, '[a-zA-Z]')"
        
        names_count = "ALL"

    logger.info(f"Targeting {names_count} unique surnames...")
    logger.info("Building population_master (Squash & Filter)...")

    logger.info("Step 1/4: Extracting Sample Patch records...")
    if is_tracer:
        # ANY 'IN' clause on a massive un-analyzed SQLite database can cause the query planner 
        # to fall back to a full table scan (which looks like a freeze).
        # To guarantee B-Tree index seeks, we execute individual equality constraints (name = 'X').
        logger.info("   -> Streaming Sample Patch records via single B-Tree seeks...")
        unique_names = list(set(name_list))

        # Create the destination table first with the correct schema using LIMIT 0 (fastest method).
        con.execute("""
            CREATE TEMP TABLE samp_filtered AS
            SELECT year, serial, pernum, 
                   MAX(namefrst) as namefrst, MAX(namelast) as namelast, MAX(birthyr) as birthyr,
                   MAX(sex) as sex, MAX(bpld) as bpld, MAX(stateicp) as stateicp
            FROM samples.population
            GROUP BY year, serial, pernum
            LIMIT 0;
        """)

        logger.info(f"   -> Processing {len(unique_names)} surnames individually...")
        for idx, name in enumerate(unique_names):
            name_safe = name.replace("'", "''")
            if (idx + 1) % 50 == 0:
                logger.info(f"      ...processed {idx + 1}/{len(unique_names)} surnames")
            con.execute(f"""
                INSERT INTO samp_filtered BY NAME
                SELECT s.year, s.serial, s.pernum, 
                       MAX(s.namefrst) as namefrst, MAX(s.namelast) as namelast, MAX(s.birthyr) as birthyr,
                       MAX(s.sex) as sex, MAX(s.bpld) as bpld, MAX(s.stateicp) as stateicp
                FROM samples.population s
                WHERE s.namelast = '{name_safe}'
                GROUP BY s.year, s.serial, s.pernum;
            """)
    else:
        con.execute(f"""
            -- Step 1: Materialize sample patch matches into memory
            CREATE TEMP TABLE samp_filtered AS
            SELECT s.year, s.serial, s.pernum, 
                   MAX(s.namefrst) as namefrst, 
                   MAX(s.namelast) as namelast,
                   MAX(s.birthyr) as birthyr,
                   MAX(s.sex) as sex,
                   MAX(s.bpld) as bpld,
                   MAX(s.stateicp) as stateicp
            FROM samples.population s
            WHERE {name_filter_samp}
            GROUP BY s.year, s.serial, s.pernum
        """)

    logger.info("Step 2/4: Extracting 100% Base records via Surname Predicate Pushdown...")
    if is_tracer:
        logger.info("   -> Streaming 100% Base records (Branch 1) via single B-Tree seeks...")
        unique_names = list(set(name_list))

        # Create the destination table with the correct schema from the source (LIMIT 0 is instant)
        con.execute("CREATE TEMP TABLE base_branch_1 AS SELECT * FROM census100.population LIMIT 0;")

        logger.info(f"   -> Processing {len(unique_names)} surnames individually...")
        for idx, name in enumerate(unique_names):
            name_safe = name.replace("'", "''")
            if (idx + 1) % 50 == 0:
                logger.info(f"      ...processed {idx + 1}/{len(unique_names)} surnames")
            con.execute(f"""
                INSERT INTO base_branch_1
                SELECT * FROM census100.population b
                WHERE b.namelast = '{name_safe}';
            """)
    else:
        con.execute(f"""
            -- Step 2: Stream the 816M base rows matching target names directly
            CREATE TEMP TABLE base_branch_1 AS
            SELECT b.* 
            FROM census100.population b
            WHERE {name_filter_base}
        """)

    logger.info("Step 3/4: Extracting Base records matching Sample Patch via Dynamic Pushdown...")
    samp_keys = con.execute("SELECT DISTINCT serial FROM samp_filtered").fetchall()
    
    if samp_keys:
        serial_list = [str(r[0]) for r in samp_keys]
        # Protect against massive IN clauses. If it's Tracer mode, we push down `serial` across SQLite interface.
        if len(serial_list) < 50000:
            if is_tracer:
                # Joining a DuckDB memory table with an 816M row SQLite table will force DuckDB
                # to pull the entire SQLite table into memory. This causes a massive freeze/crash.
                # We must use individual B-Tree seeks on the serial column directly into a temp table.
                logger.info("   -> Streaming Base records (Branch 2) via single B-Tree seeks...")
                con.execute("CREATE TEMP TABLE base_branch_2_raw AS SELECT * FROM census100.population LIMIT 0;")
                
                unique_serials = list(set([r[0] for r in samp_keys]))
                logger.info(f"   -> Processing {len(unique_serials)} serial keys individually...")
                
                for idx, s_val in enumerate(unique_serials):
                    if (idx + 1) % 5000 == 0:
                        logger.info(f"      ...processed {idx + 1}/{len(unique_serials)} serials")
                    con.execute(f"""
                        INSERT INTO base_branch_2_raw
                        SELECT * FROM census100.population b
                        WHERE b.serial = {s_val};
                    """)

                logger.info("   -> Filtering Base Branch 2 locally...")
                con.execute("""
                    CREATE TEMP TABLE base_branch_2 AS
                    SELECT b.* 
                    FROM base_branch_2_raw b
                    INNER JOIN samp_filtered s 
                      ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum
                    WHERE b.namelast IS NULL OR NOT REGEXP_MATCHES(b.namelast, '[a-zA-Z]')
                """)
                con.execute("DROP TABLE base_branch_2_raw;")
            else:
                serial_clause_b = "b.serial IN (" + ",".join(serial_list) + ")"
                con.execute(f"""
                    CREATE TEMP TABLE base_branch_2 AS
                    SELECT b.* 
                    FROM census100.population b
                    INNER JOIN samp_filtered s 
                      ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum
                    WHERE {serial_clause_b} AND (b.namelast IS NULL OR NOT REGEXP_MATCHES(b.namelast, '[a-zA-Z]'))
                """)
        else:
            con.execute("""
                CREATE TEMP TABLE base_branch_2 AS
                SELECT b.* 
                FROM census100.population b
                INNER JOIN samp_filtered s 
                  ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum
                WHERE b.namelast IS NULL OR NOT REGEXP_MATCHES(b.namelast, '[a-zA-Z]')
            """)
    else:
        con.execute("CREATE TEMP TABLE base_branch_2 AS SELECT * FROM census100.population WHERE 1=0")

    # Step 4: We build the final in-memory table that maps IPUMS variables to Splink standard names
    logger.info("Step 4/4: Constructing population_master from extracted branches...")
    con.execute(f"""
        CREATE TABLE population_master AS
        WITH collapsed_census AS (
            SELECT 
                b.composite_id AS unique_id,
                COALESCE(s.namefrst, b.namefrst) AS first_name,
                COALESCE(s.namelast, b.namelast) AS last_name,
                NULLIF(CAST(COALESCE(s.birthyr, b.birthyr) AS INTEGER), 9999) AS birth_year,
                COALESCE(s.stateicp, b.stateicp) AS state,
                COALESCE(s.sex, b.sex) AS sex,
                COALESCE(s.bpld, b.bpld) AS birth_place,
                CAST(b.year AS INTEGER) AS census_year,
                CAST(NULL AS VARCHAR) AS death_date,
                'census' AS source_db,
                CASE WHEN TRY_CAST(b.poploc AS INTEGER) > 0 
                     THEN SPLIT_PART(b.composite_id, '_', 1) || '_' || SPLIT_PART(b.composite_id, '_', 2) || '_' || b.poploc 
                     ELSE NULL END AS father_pointer,
                CASE WHEN TRY_CAST(b.momloc AS INTEGER) > 0 
                     THEN SPLIT_PART(b.composite_id, '_', 1) || '_' || SPLIT_PART(b.composite_id, '_', 2) || '_' || b.momloc 
                     ELSE NULL END AS mother_pointer
            FROM base_branch_1 b
            LEFT JOIN samp_filtered s
              ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum

            UNION ALL

            SELECT 
                b.composite_id AS unique_id,
                COALESCE(s.namefrst, b.namefrst) AS first_name,
                COALESCE(s.namelast, b.namelast) AS last_name,
                NULLIF(CAST(COALESCE(s.birthyr, b.birthyr) AS INTEGER), 9999) AS birth_year,
                COALESCE(s.stateicp, b.stateicp) AS state,
                COALESCE(s.sex, b.sex) AS sex,
                COALESCE(s.bpld, b.bpld) AS birth_place,
                CAST(b.year AS INTEGER) AS census_year,
                CAST(NULL AS VARCHAR) AS death_date,
                'census' AS source_db,
                CASE WHEN TRY_CAST(b.poploc AS INTEGER) > 0 
                     THEN SPLIT_PART(b.composite_id, '_', 1) || '_' || SPLIT_PART(b.composite_id, '_', 2) || '_' || b.poploc 
                     ELSE NULL END AS father_pointer,
                CASE WHEN TRY_CAST(b.momloc AS INTEGER) > 0 
                     THEN SPLIT_PART(b.composite_id, '_', 1) || '_' || SPLIT_PART(b.composite_id, '_', 2) || '_' || b.momloc 
                     ELSE NULL END AS mother_pointer
            FROM base_branch_2 b
            INNER JOIN samp_filtered s
              ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum
        )
        SELECT c.* FROM collapsed_census c
        WHERE c.last_name IS NOT NULL AND REGEXP_MATCHES(c.last_name, '[a-zA-Z]')
          AND c.first_name IS NOT NULL AND REGEXP_MATCHES(c.first_name, '[a-zA-Z]')
        UNION ALL
        SELECT 
            'DEATH_' || CAST(b_r.record_id AS VARCHAR) AS unique_id,
            b_r.first AS first_name,
            b_r.last AS last_name,
            TRY_CAST(SUBSTR(b_r.dob, 1, 4) AS INTEGER) AS birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS VARCHAR) AS sex,
            CAST(NULL AS VARCHAR) AS birth_place,
            CAST(NULL AS INTEGER) AS census_year,
            b_r.dod AS death_date,
            'death_index' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM birls.birls_records b_r
        WHERE {name_filter_birls} AND b_r.first IS NOT NULL AND REGEXP_MATCHES(b_r.first, '[a-zA-Z]')
        UNION ALL
        SELECT 
            'UNIDEATH_' || u_d.record_id AS unique_id,
            u_d.first_name,
            u_d.last_name,
            u_d.birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS VARCHAR) AS sex,
            CAST(NULL AS VARCHAR) AS birth_place,
            CAST(NULL AS INTEGER) AS census_year,
            CAST(u_d.death_year AS VARCHAR) AS death_date,
            'death_index' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM birls.universal_death_index u_d
        WHERE {name_filter_uni} AND u_d.first_name IS NOT NULL AND REGEXP_MATCHES(u_d.first_name, '[a-zA-Z]')
        UNION ALL
        SELECT 
            'GED_' || g_r.gedcom_id AS unique_id,
            g_r.first_name,
            g_r.last_name,
            g_r.birth_year,
            CAST(NULL AS VARCHAR) AS state,
            CAST(NULL AS VARCHAR) AS sex,
            g_r.birth_place,
            CAST(NULL AS INTEGER) AS census_year,
            g_r.death_date,
            'gedcom' AS source_db,
            CAST(NULL AS VARCHAR) AS father_pointer,
            CAST(NULL AS VARCHAR) AS mother_pointer
        FROM gedcom.gedcom_records g_r
        WHERE {name_filter_gedcom} AND g_r.first_name IS NOT NULL AND REGEXP_MATCHES(g_r.first_name, '[a-zA-Z]')
    """)

    row_count = con.execute("SELECT COUNT(*) FROM population_master").fetchone()[0]
    logger.info(f"Successfully extracted {row_count:,} records nationwide.")

    # ---------------------------------------------------------
    # PHASE 2: GOLDEN RECORD GENERATION (SPLINK)
    # ---------------------------------------------------------
    logger.info("Initializing Splink Linker...")

    if mode in ("train", "both"):
        logger.info("Setting up view for TRAINING (using full dataset)...")
        con.execute("CREATE OR REPLACE VIEW population_for_splink AS SELECT * FROM population_master;")
        generator = CreateGoldenRecord(db_connection=con, logger=logger)
        generator.run(mode="train", output_table="clean.golden_records", model_path=SPLINK_MODEL_JSON)
        if mode == "train":
            return

    if mode in ("link", "both"):
        if is_tracer:
            slices = sorted([r[0] for r in con.execute("SELECT DISTINCT SUBSTR(namelast, 1, 1) FROM target_names").fetchall()])
        else:
            slices = list(string.ascii_uppercase) + ["OTHER"]

        # Auto-Resume Logic: Find which letters are already finished in the Clean Vault
        try:
            completed_letters = [r[0] for r in con.execute(
                "SELECT DISTINCT UPPER(SUBSTR(last_name, 1, 1)) FROM clean.golden_records").fetchall()]
        except Exception:
            completed_letters = []

        for letter in slices:
            if letter in completed_letters and not is_tracer:
                logger.info(f"*** Slice '{letter}' already exists in Clean Vault. Skipping! (Auto-Resume) ***")
                continue

            logger.info(f"\n{'=' * 60}\n--- Slicing Data: Last Names starting with '{letter}' ---\n{'=' * 60}")

            if letter == "OTHER":
                # Catch names starting with numbers, quotes, or special characters
                letters_list = "', '".join(list(string.ascii_uppercase))
                condition = f"UPPER(SUBSTR(last_name, 1, 1)) NOT IN ('{letters_list}')"
            else:
                condition = f"UPPER(SUBSTR(last_name, 1, 1)) = '{letter}'"

            con.execute(
                f"CREATE OR REPLACE VIEW population_for_splink AS SELECT * FROM population_master WHERE {condition};")

            slice_count = con.execute("SELECT COUNT(*) FROM population_for_splink").fetchone()[0]
            if slice_count == 0:
                logger.info(f"  -> No records found for '{letter}'. Skipping.")
                continue

            logger.info(f"  -> Processing {slice_count:,} records for slice '{letter}'...")
            generator = CreateGoldenRecord(db_connection=con, logger=logger)
            generator.run(mode="link", output_table="clean.golden_records", model_path=SPLINK_MODEL_JSON)

        logger.info("\nAll slices completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Phase 2 Analyst Pipeline.")
    parser.add_argument("--mode", choices=["train", "link", "both"], default="link",
                        help="Pipeline mode: 'train' (train AI only), 'link' (cluster using saved model), or 'both'.")
    parser.add_argument("--test", action="store_true",
                        help="Run against MasterVault_TEST.db and output to CleanVault_TEST.db")
    parser.add_argument("--tracer", action="store_true",
                        help="Run in tracer bullet mode (only processes surnames found in GedcomVault.db)")
    args = parser.parse_args()

    main_logger = gen_logging.setup_logging(logger_name="ANALYST")
    run_analyst_pipeline(main_logger, mode=args.mode, is_test=args.test, is_tracer=args.tracer)
