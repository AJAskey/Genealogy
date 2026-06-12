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

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import argparse
import os
import string
import sys

import duckdb
import pandas as pd

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
        target_names_df = con.execute(
            "SELECT DISTINCT last_name FROM gedcom.gedcom_records WHERE last_name IS NOT NULL AND REGEXP_MATCHES(last_name, '[a-zA-Z]')").df()

        name_list = []
        for name in target_names_df.iloc[:, 0].tolist():
            name = str(name).strip()
            name_list.append(name.upper())
            name_list.append(name.capitalize())
            name_list.append(name.lower())

        unique_names = list(set(name_list))
        names_df = pd.DataFrame(unique_names, columns=['namelast'])
        con.register('df_target_names', names_df)

        con.execute("CREATE TEMP TABLE target_names AS SELECT * FROM df_target_names;")
        names_count = len(unique_names)
    else:
        logger.info("NATIONWIDE MODE: Processing ALL valid records...")
        names_count = "ALL"

    logger.info(f"Targeting {names_count} unique surnames...")
    logger.info("Building population_master (Squash & Filter)...")

    logger.info("Step 1/3: Extracting Sample Patch records (Scans 40M rows - takes ~10 seconds)...")
    if is_tracer:
        con.execute("""
                    CREATE
                    TEMP TABLE samp_filtered AS
                    SELECT s.year,
                           s.serial,
                           s.pernum,
                           MAX(s.namefrst) as namefrst,
                           MAX(s.namelast) as namelast,
                           MAX(s.birthyr)  as birthyr,
                           MAX(s.sex)      as sex,
                           MAX(s.bpld)     as bpld,
                           MAX(s.stateicp) as stateicp
                    FROM samples.population s
                             INNER JOIN target_names t ON s.namelast = t.namelast
                    GROUP BY s.year, s.serial, s.pernum
                    """)
    else:
        con.execute(f"""
            CREATE TEMP TABLE samp_filtered AS
            SELECT s.year, s.serial, s.pernum, 
                   MAX(s.namefrst) as namefrst, 
                   MAX(s.namelast) as namelast,
                   MAX(s.birthyr) as birthyr,
                   MAX(s.sex) as sex,
                   MAX(s.bpld) as bpld,
                   MAX(s.stateicp) as stateicp
            FROM samples.population s
            WHERE s.namelast IS NOT NULL AND REGEXP_MATCHES(s.namelast, '[a-zA-Z]')
            GROUP BY s.year, s.serial, s.pernum
        """)

    logger.info(
        "Step 2/3: Extracting Base records (Scans 816M rows - THIS WILL TAKE 2 TO 6 MINUTES. DO NOT CANCEL!)...")

    con.execute("""
        CREATE TEMP TABLE temp_serial_keys AS
        SELECT DISTINCT serial FROM samp_filtered
    """)

    if is_tracer:
        con.execute("""
            CREATE TEMP TABLE base_filtered AS
            SELECT b.* 
            FROM census100.population b
            LEFT JOIN target_names t ON b.namelast = t.namelast
            LEFT JOIN temp_serial_keys tsk ON b.serial = tsk.serial
            WHERE t.namelast IS NOT NULL OR tsk.serial IS NOT NULL
        """)
    else:
        con.execute("""
                    CREATE
                    TEMP TABLE base_filtered AS
                    SELECT b.*
                    FROM census100.population b
                             LEFT JOIN temp_serial_keys tsk ON b.serial = tsk.serial
                    WHERE (b.namelast IS NOT NULL AND REGEXP_MATCHES(b.namelast, '[a-zA-Z]'))
                       OR tsk.serial IS NOT NULL
                    """)

    logger.info("Step 3/3: Constructing population_master from extracted branches...")
    if is_tracer:
        con.execute("""
                    CREATE TABLE population_master AS
                    WITH collapsed_census AS (SELECT b.composite_id                                                AS unique_id,
                                                     COALESCE(s.namefrst, b.namefrst)                              AS first_name,
                                                     COALESCE(s.namelast, b.namelast)                              AS last_name,
                                                     NULLIF(CAST(COALESCE(s.birthyr, b.birthyr) AS INTEGER), 9999) AS birth_year,
                                                     COALESCE(s.stateicp, b.stateicp)                              AS state,
                                                     COALESCE(s.sex, b.sex)                                        AS sex,
                                                     COALESCE(s.bpld, b.bpld)                                      AS birth_place,
                                                     CAST(b.year AS INTEGER)                                       AS census_year,
                                                     CAST(NULL AS VARCHAR)                                         AS death_date,
                                                     'census'                                                      AS source_db,
                                                     CASE
                                                         WHEN TRY_CAST(b.poploc AS INTEGER) > 0
                                                             THEN SPLIT_PART(b.composite_id, '_', 1) || '_' ||
                                                                  SPLIT_PART(b.composite_id, '_', 2) || '_' || b.poploc
                                                         ELSE NULL END                                             AS father_pointer,
                                                     CASE
                                                         WHEN TRY_CAST(b.momloc AS INTEGER) > 0
                                                             THEN SPLIT_PART(b.composite_id, '_', 1) || '_' ||
                                                                  SPLIT_PART(b.composite_id, '_', 2) || '_' || b.momloc
                                                         ELSE NULL END                                             AS mother_pointer
                                              FROM base_filtered b
                                                       LEFT JOIN samp_filtered s
                                                                 ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum)
                    SELECT c.*
                    FROM collapsed_census c
                    WHERE c.last_name IS NOT NULL
                      AND REGEXP_MATCHES(c.last_name, '[a-zA-Z]')
                      AND c.first_name IS NOT NULL
                      AND REGEXP_MATCHES(c.first_name, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'DEATH_' || CAST(b_r.record_id AS VARCHAR) AS unique_id,
                           b_r.first                                  AS first_name,
                           b_r.last                                   AS last_name,
                           TRY_CAST(SUBSTR(b_r.dob, 1, 4) AS INTEGER) AS birth_year,
                           CAST(NULL AS VARCHAR)                      AS state,
                           CAST(NULL AS VARCHAR)                      AS sex,
                           CAST(NULL AS VARCHAR)                      AS birth_place,
                           CAST(NULL AS INTEGER)                      AS census_year,
                           b_r.dod                                    AS death_date,
                           'death_index'                              AS source_db,
                           CAST(NULL AS VARCHAR)                      AS father_pointer,
                           CAST(NULL AS VARCHAR)                      AS mother_pointer
                    FROM birls.birls_records b_r
                             INNER JOIN target_names t ON b_r.last = t.namelast
                    WHERE b_r.first IS NOT NULL
                      AND REGEXP_MATCHES(b_r.first, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'UNIDEATH_' || u_d.record_id    AS unique_id,
                           u_d.first_name,
                           u_d.last_name,
                           u_d.birth_year,
                           CAST(NULL AS VARCHAR)           AS state,
                           CAST(NULL AS VARCHAR)           AS sex,
                           CAST(NULL AS VARCHAR)           AS birth_place,
                           CAST(NULL AS INTEGER)           AS census_year,
                           CAST(u_d.death_year AS VARCHAR) AS death_date,
                           'death_index'                   AS source_db,
                           CAST(NULL AS VARCHAR)           AS father_pointer,
                           CAST(NULL AS VARCHAR)           AS mother_pointer
                    FROM birls.universal_death_index u_d
                             INNER JOIN target_names t ON u_d.last_name = t.namelast
                    WHERE u_d.first_name IS NOT NULL
                      AND REGEXP_MATCHES(u_d.first_name, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'GED_' || g_r.gedcom_id AS unique_id,
                           g_r.first_name,
                           g_r.last_name,
                           g_r.birth_year,
                           CAST(NULL AS VARCHAR)   AS state,
                           CAST(NULL AS VARCHAR)   AS sex,
                           g_r.birth_place,
                           CAST(NULL AS INTEGER)   AS census_year,
                           g_r.death_date,
                           'gedcom'                AS source_db,
                           CAST(NULL AS VARCHAR)   AS father_pointer,
                           CAST(NULL AS VARCHAR)   AS mother_pointer
                    FROM gedcom.gedcom_records g_r
                             INNER JOIN target_names t ON g_r.last_name = t.namelast
                    WHERE g_r.first_name IS NOT NULL
                      AND REGEXP_MATCHES(g_r.first_name, '[a-zA-Z]')
                    """)
    else:
        con.execute("""
                    CREATE TABLE population_master AS
                    WITH collapsed_census AS (SELECT b.composite_id                                                AS unique_id,
                                                     COALESCE(s.namefrst, b.namefrst)                              AS first_name,
                                                     COALESCE(s.namelast, b.namelast)                              AS last_name,
                                                     NULLIF(CAST(COALESCE(s.birthyr, b.birthyr) AS INTEGER), 9999) AS birth_year,
                                                     COALESCE(s.stateicp, b.stateicp)                              AS state,
                                                     COALESCE(s.sex, b.sex)                                        AS sex,
                                                     COALESCE(s.bpld, b.bpld)                                      AS birth_place,
                                                     CAST(b.year AS INTEGER)                                       AS census_year,
                                                     CAST(NULL AS VARCHAR)                                         AS death_date,
                                                     'census'                                                      AS source_db,
                                                     CASE
                                                         WHEN TRY_CAST(b.poploc AS INTEGER) > 0
                                                             THEN SPLIT_PART(b.composite_id, '_', 1) || '_' ||
                                                                  SPLIT_PART(b.composite_id, '_', 2) || '_' || b.poploc
                                                         ELSE NULL END                                             AS father_pointer,
                                                     CASE
                                                         WHEN TRY_CAST(b.momloc AS INTEGER) > 0
                                                             THEN SPLIT_PART(b.composite_id, '_', 1) || '_' ||
                                                                  SPLIT_PART(b.composite_id, '_', 2) || '_' || b.momloc
                                                         ELSE NULL END                                             AS mother_pointer
                                              FROM base_filtered b
                                                       LEFT JOIN samp_filtered s
                                                                 ON b.year = s.year AND b.serial = s.serial AND b.pernum = s.pernum)
                    SELECT c.*
                    FROM collapsed_census c
                    WHERE c.last_name IS NOT NULL
                      AND REGEXP_MATCHES(c.last_name, '[a-zA-Z]')
                      AND c.first_name IS NOT NULL
                      AND REGEXP_MATCHES(c.first_name, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'DEATH_' || CAST(b_r.record_id AS VARCHAR) AS unique_id,
                           b_r.first                                  AS first_name,
                           b_r.last                                   AS last_name,
                           TRY_CAST(SUBSTR(b_r.dob, 1, 4) AS INTEGER) AS birth_year,
                           CAST(NULL AS VARCHAR)                      AS state,
                           CAST(NULL AS VARCHAR)                      AS sex,
                           CAST(NULL AS VARCHAR)                      AS birth_place,
                           CAST(NULL AS INTEGER)                      AS census_year,
                           b_r.dod                                    AS death_date,
                           'death_index'                              AS source_db,
                           CAST(NULL AS VARCHAR)                      AS father_pointer,
                           CAST(NULL AS VARCHAR)                      AS mother_pointer
                    FROM birls.birls_records b_r
                    WHERE b_r.last IS NOT NULL
                      AND REGEXP_MATCHES(b_r.last, '[a-zA-Z]')
                      AND b_r.first IS NOT NULL
                      AND REGEXP_MATCHES(b_r.first, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'UNIDEATH_' || u_d.record_id    AS unique_id,
                           u_d.first_name,
                           u_d.last_name,
                           u_d.birth_year,
                           CAST(NULL AS VARCHAR)           AS state,
                           CAST(NULL AS VARCHAR)           AS sex,
                           CAST(NULL AS VARCHAR)           AS birth_place,
                           CAST(NULL AS INTEGER)           AS census_year,
                           CAST(u_d.death_year AS VARCHAR) AS death_date,
                           'death_index'                   AS source_db,
                           CAST(NULL AS VARCHAR)           AS father_pointer,
                           CAST(NULL AS VARCHAR)           AS mother_pointer
                    FROM birls.universal_death_index u_d
                    WHERE u_d.last_name IS NOT NULL
                      AND REGEXP_MATCHES(u_d.last_name, '[a-zA-Z]')
                      AND u_d.first_name IS NOT NULL
                      AND REGEXP_MATCHES(u_d.first_name, '[a-zA-Z]')
                    UNION ALL
                    SELECT 'GED_' || g_r.gedcom_id AS unique_id,
                           g_r.first_name,
                           g_r.last_name,
                           g_r.birth_year,
                           CAST(NULL AS VARCHAR)   AS state,
                           CAST(NULL AS VARCHAR)   AS sex,
                           g_r.birth_place,
                           CAST(NULL AS INTEGER)   AS census_year,
                           g_r.death_date,
                           'gedcom'                AS source_db,
                           CAST(NULL AS VARCHAR)   AS father_pointer,
                           CAST(NULL AS VARCHAR)   AS mother_pointer
                    FROM gedcom.gedcom_records g_r
                    WHERE g_r.last_name IS NOT NULL
                      AND REGEXP_MATCHES(g_r.last_name, '[a-zA-Z]')
                      AND g_r.first_name IS NOT NULL
                      AND REGEXP_MATCHES(g_r.first_name, '[a-zA-Z]')
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
            slices = sorted(
                [r[0] for r in con.execute("SELECT DISTINCT SUBSTR(namelast, 1, 1) FROM target_names").fetchall()])
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
