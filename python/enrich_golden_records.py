"""
-----------------------------------
File: enrich_golden_records.py

Summary: Takes flattened GEDCOM CSV data and safely merges new facts into 
         the CleanVault Golden Records using Splink 'link_only' mode.
         
         Applies strict survivorship: Existing Golden Record data (like 
         birth/death dates) is NEVER overwritten. New data is only 
         appended if the Golden Record's field is currently NULL.
-----------------------------------
"""

import os
import duckdb
import splink.comparison_library as cl
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CLEAN_DB = r"D:\Data\Genealogy_Data\CleanVault.db"
GEDCOM_CSV = r"E:\Users\Andy\PycharmProjects\Genealogy\output\thom.csv"
MATCH_THRESHOLD = 0.95  # Must be 95% confident to merge facts!


def run_enrichment(logger):
    logger.info("Initializing DuckDB Engine for Enrichment...")
    con = duckdb.connect(database=':memory:')
    con.execute("PRAGMA memory_limit='90GB';")
    
    logger.info("Loading SQLite scanner extension...")
    con.execute("INSTALL sqlite; LOAD sqlite;")
    
    logger.info(f"Attaching Clean Vault: {CLEAN_DB}")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE);")

    # ---------------------------------------------------------
    # 1. PREP THE GEDCOM CSV DATA
    # ---------------------------------------------------------
    logger.info(f"Loading and formatting GEDCOM CSV: {GEDCOM_CSV}")
    
    # We format the CSV on the fly to match the Golden Records structure.
    # - split_part() is used to extract first and last names from 'full_name'
    # - Right-most 4 chars of birth_date usually contain the year in GEDCOMs
    con.execute(f"""
        CREATE TABLE aux_data AS
        SELECT 
            gedcom_id AS unique_id,
            TRIM(split_part(full_name, ' ', 1)) AS first_name,
            TRIM(split_part(full_name, ' ', -1)) AS last_name,
            TRY_CAST(SUBSTR(TRIM(birth_date), -4) AS INTEGER) AS birth_year,
            death_date AS aux_death_date,
            birth_place AS aux_birth_place
        FROM read_csv_auto('{GEDCOM_CSV}')
        WHERE full_name IS NOT NULL
    """)
    
    aux_count = con.execute("SELECT COUNT(*) FROM aux_data").fetchone()[0]
    logger.info(f"Loaded {aux_count:,} auxiliary GEDCOM records.")

    # ---------------------------------------------------------
    # 2. PREP THE GOLDEN RECORDS
    # ---------------------------------------------------------
    logger.info("Loading Golden Records for comparison...")
    con.execute("""
        CREATE TABLE golden_stage AS
        SELECT 
            cluster_id AS unique_id,
            first_name,
            last_name,
            birth_year,
            death_date
        FROM clean.golden_records
    """)

    # ---------------------------------------------------------
    # 3. SPLINK 'LINK_ONLY' MATCHING
    # ---------------------------------------------------------
    logger.info("Configuring Splink for Link-Only matching...")
    
    settings = SettingsCreator(
        link_type="link_only",
        comparisons=[
            cl.LevenshteinAtThresholds("first_name", [1, 2]),
            cl.JaroWinklerAtThresholds("last_name", [0.88, 0.95]),
            cl.ExactMatch("birth_year")
        ],
        blocking_rules_to_generate_predictions=[
            block_on("first_name", "last_name"),
            block_on("last_name", "birth_year"),
        ],
        max_iterations=10,
    )
    
    db_api = DuckDBAPI(connection=con)
    # Notice we pass TWO tables now: Table A (Golden) and Table B (Aux)
    linker = Linker(["golden_stage", "aux_data"], settings, db_api=db_api)
    
    logger.info("Training AI on matching mechanics...")
    linker.training.estimate_u_using_random_sampling(max_pairs=1e6)
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("first_name", "last_name"))
    linker.training.estimate_parameters_using_expectation_maximisation(block_on("last_name", "birth_year"))
    
    logger.info(f"Predicting cross-database matches at {MATCH_THRESHOLD * 100}% confidence...")
    predictions = linker.inference.predict(threshold_match_probability=MATCH_THRESHOLD)
    
    # Materialize the predicted matches into DuckDB so we can use standard SQL on them
    con.register("high_confidence_matches", predictions.as_duckdb_relation())
    
    # ---------------------------------------------------------
    # 4. SAFE MERGE (SURVIVORSHIP)
    # ---------------------------------------------------------
    logger.info("Safely merging new facts into Golden Records (No-Overwrite Policy)...")
    
    # COALESCE(A, B) means: "If A is not null, keep A. Otherwise, use B."
    # unique_id_l is the left table (Golden Records). unique_id_r is the right table (Aux Data).
    con.execute("""
        UPDATE clean.golden_records
        SET 
            death_date = COALESCE(clean.golden_records.death_date, aux.aux_death_date)
        FROM high_confidence_matches p
        JOIN aux_data aux ON p.unique_id_r = aux.unique_id
        WHERE clean.golden_records.cluster_id = p.unique_id_l;
    """)
    
    logger.info("Enrichment complete! Golden Records safely updated.")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="ENRICHMENT")
    run_enrichment(main_logger)