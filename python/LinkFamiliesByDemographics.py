"""
-----------------------------------
File: LinkFamiliesByDemographics.py

Summary: "The Time Machine"
         Finds nameless families in one decade and mathematically links them 
         to the next decade based on Household Signatures (Head & Spouse ages +10, 
         Birthplaces, and Parent Birthplaces [FBPL/MBPL]).
-----------------------------------
"""

import os

import duckdb

from python.utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MASTER_100_DB = os.path.join(BASE_DATA_DIR, "MasterVault_ALL.db")
CLEAN_DB = os.path.join(BASE_DATA_DIR, "CleanVault.db")
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")


def link_households_across_decades(logger):
    logger.info("Initializing DuckDB... Finding demographic household matches across ALL consecutive decades.")

    # Check for file locks
    if os.path.exists(MATCH_DB):
        try:
            os.remove(MATCH_DB)
        except PermissionError:
            logger.warning(f"CRITICAL: {MATCH_DB} is locked by another program (likely a DB Viewer).")
            logger.warning("Please close any applications using this database and try again.")
            return

    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='90GB'")
    con.execute("INSTALL sqlite; LOAD sqlite;")

    logger.info("Attaching Vaults...")
    con.execute(f"ATTACH '{MASTER_100_DB}' AS base (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{CLEAN_DB}' AS clean (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE);")

    logger.info("Running pure SQL demographic vector match... This will take a few minutes.")

    logger.info("Step 1/5: Extracting Pointers from Golden Records...")
    con.execute("""
                CREATE
                TEMP TABLE clean_ptrs AS
                SELECT DISTINCT UNNEST(string_split(vault_pointers, '|')) AS comp_id
                FROM clean.golden_records;
                """)

    logger.info("Step 2/5: Extracting Head & Spouse population from massive census...")
    con.execute("""
                CREATE
                TEMP TABLE pop AS
                SELECT composite_id,
                       CAST(year AS INTEGER) AS year, serial, related, 
               TRY_CAST(age AS INTEGER) as age, bpld, fbpl, mbpl
                FROM base.population
                WHERE age IS NOT NULL
                  AND bpld IS NOT NULL
                  AND (related IN ('0100'
                    , '0200'
                    , '100'
                    , '200'
                    , 'Head'
                    , 'Spouse'
                    , 'Wife')
                   OR related ILIKE '%Head%'
                   OR related ILIKE '%Spouse%'
                   OR related ILIKE '%Wife%');
                """)

    logger.info("Step 3/5: Pairing up Households (Head + Spouse)...")
    con.execute("""
                CREATE
                TEMP TABLE hh_all AS
                SELECT h.year,
                       h.serial,
                       h.composite_id AS head_id,
                       h.age          AS head_age,
                       h.bpld         AS head_bpld,
                       h.fbpl         AS head_fbpl,
                       h.mbpl         AS head_mbpl,
                       s.composite_id AS spouse_id,
                       s.age          AS spouse_age,
                       s.bpld         AS spouse_bpld,
                       s.fbpl         AS spouse_fbpl,
                       s.mbpl         AS spouse_mbpl
                FROM pop h
                         JOIN pop s ON h.serial = s.serial AND h.year = s.year
                    AND
                                       (s.related IN ('0200', '200', 'Spouse', 'Wife') OR s.related ILIKE '%Spouse%' OR s.related ILIKE '%Wife%')
                WHERE (h.related IN ('0100', '100', 'Head') OR h.related ILIKE '%Head%');
                """)

    logger.info("Step 4/5: Isolating Golden Anchored Households (The targets)...")
    con.execute("""
                CREATE
                TEMP TABLE anchored_hh AS
                SELECT *,
                       CAST(year + 10 AS INTEGER) AS target_year,
                       head_age + 8               AS min_head_age,
                       head_age + 12              AS max_head_age,
                       spouse_age + 8             AS min_spouse_age,
                       spouse_age + 12            AS max_spouse_age
                FROM hh_all
                WHERE head_id IN (SELECT comp_id FROM clean_ptrs)
                UNION
                SELECT *,
                       CAST(year + 10 AS INTEGER) AS target_year,
                       head_age + 8               AS min_head_age,
                       head_age + 12              AS max_head_age,
                       spouse_age + 8             AS min_spouse_age,
                       spouse_age + 12            AS max_spouse_age
                FROM hh_all
                WHERE spouse_id IN (SELECT comp_id FROM clean_ptrs);
                """)

    logger.info("Step 5/5: Bridging the Decades (The Time Machine)...")
    con.execute("""
                CREATE TABLE match_db.household_links AS
                SELECT y1.year        AS Year_1,
                       y2.year        AS Year_2,
                       y1.serial      AS Household_1,
                       y2.serial      AS Household_2,
                       y1.head_bpld   AS Head_Birthplace,
                       y1.spouse_bpld AS Spouse_Birthplace,
                       y1.head_age    AS Head_Age_1,
                       y2.head_age    AS Head_Age_2,
                       y1.spouse_age  AS Spouse_Age_1,
                       y2.spouse_age  AS Spouse_Age_2,
                       y1.head_id     AS Head_CompID_1,
                       y2.head_id     AS Head_CompID_2,
                       y1.spouse_id   AS Spouse_CompID_1,
                       y2.spouse_id   AS Spouse_CompID_2
                FROM anchored_hh y1
                         JOIN hh_all y2
                              ON y1.target_year = y2.year
                                  AND y1.head_bpld = y2.head_bpld
                                  AND y1.spouse_bpld = y2.spouse_bpld
                                  AND y2.head_age BETWEEN y1.min_head_age AND y1.max_head_age
                                  AND y2.spouse_age BETWEEN y1.min_spouse_age AND y1.max_spouse_age
                WHERE (y1.head_fbpl = y2.head_fbpl OR y1.head_fbpl IS NULL OR y2.head_fbpl IS NULL)
                  AND (y1.head_mbpl = y2.head_mbpl OR y1.head_mbpl IS NULL OR y2.head_mbpl IS NULL)
                  AND (y1.spouse_fbpl = y2.spouse_fbpl OR y1.spouse_fbpl IS NULL OR y2.spouse_fbpl IS NULL)
                  AND (y1.spouse_mbpl = y2.spouse_mbpl OR y1.spouse_mbpl IS NULL OR y2.spouse_mbpl IS NULL);
                """)

    match_count = con.execute("SELECT COUNT(*) FROM match_db.household_links").fetchone()[0]
    logger.info(f"SUCCESS! Found {match_count:,} nameless households successfully linked across decades.")
    logger.info(f"Saved to: {MATCH_DB}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="DEMO_LINK")
    link_households_across_decades(main_logger)
