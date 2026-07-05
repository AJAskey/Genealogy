"""
-----------------------------------
File: LinkFamiliesByDemographics.py
Summary: The V4 Time Machine Builder.
         Connects to all yearly census vaults, uses GEDCOM JSON targets
         to extract only relevant candidate families (Target-Driven),
         groups them into Clans using PRE-COMPUTED vault hashes,
         stitches child/adult records together,
         and consolidates all relevant data into a single Time Machine DB.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude

License: Apache License 2.0
-----------------------------------
"""
import duckdb
import os
import sys
import json
import csv
from collections import defaultdict, deque

# Dynamically add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(python_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
MATCH_DB_PATH = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
DEBUG_SURNAME = None  # Disabled: Names no longer exist in the V4 schema


# ==============================================================================

def step_1_attach_databases(con, logger):
    """Attaches all yearly SQLite vaults to the in-memory DuckDB instance."""
    logger.info(f"STEP 1: ATTACHING ALL YEARLY VAULTS FROM {YEARLY_VAULT_DIR}...")
    con.execute("INSTALL sqlite; LOAD sqlite; SET sqlite_all_varchar=true;")

    attached_dbs = 0
    for year in range(1850, 1960, 10):
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{year}.db")
        if os.path.exists(db_path):
            con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")
            logger.info(f"  -> Attached YearVault_{year}.db")
            attached_dbs += 1

    if attached_dbs == 0:
        logger.error("CRITICAL: No YearlyVault databases were found. Aborting.")
        sys.exit(1)
    logger.info("  -> Step 1 complete. All available vaults are connected.")


def step_2_extract_census_data(con, logger):
    """
    Extracts ALL families directly from the deterministic census vaults.
    No probabilistic GEDCOM targets are used here. This is pure census truth.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 2: EXTRACTING ALL CENSUS DATA (PURE DETERMINISTIC)...")
    logger.info("=====================================================================")

    # Pre-flight check to ensure hash tables exist before we do any heavy lifting.
    logger.info("  -> Performing pre-flight check for computed hash tables...")
    try:
        # We only need to check one vault. If 1850 has it, they all should.
        con.execute("SELECT 1 FROM vault_1850.computed_fam_hashes LIMIT 1;")
        logger.info("     [OK] Hash tables found. Proceeding with extraction.")
    except duckdb.CatalogException:
        logger.error("CRITICAL: The 'computed_fam_hashes' table was not found in YearVault_1850.db.")
        logger.error("          This likely means the 'BuildVaultHashes.py' script has not been run on this dataset.")
        logger.error("          Please run the overnight hash builder script on this data directory and try again.")
        sys.exit(1)

    con.execute("""
        CREATE TEMP TABLE all_families AS 
        SELECT f.family_id, f.head_histid, f.spouse_histid, h.family_hash, h.snapshot_fam_hash 
        FROM vault_1850.families f 
        JOIN vault_1850.computed_fam_hashes h ON f.family_id = h.family_id 
        WHERE 1=0;
    """)

    for year in range(1850, 1960, 10):
        if not con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            continue

        # Force a sequential bulk-read into DuckDB RAM to completely bypass slow SQLite index lookups
        con.execute(f"""
            CREATE TEMP TABLE local_fams AS SELECT family_id, head_histid, spouse_histid FROM vault_{year}.families;
            CREATE TEMP TABLE local_hashes AS SELECT family_id, family_hash, snapshot_fam_hash FROM vault_{year}.computed_fam_hashes;
        """)

        con.execute(f"""
            INSERT INTO all_families
            SELECT f.family_id, f.head_histid, f.spouse_histid, lh.family_hash, lh.snapshot_fam_hash
            FROM local_fams f
            JOIN local_hashes lh ON f.family_id = lh.family_id;
        """)

        con.execute("DROP TABLE local_fams;")
        con.execute("DROP TABLE local_hashes;")

        count = con.execute(f"SELECT COUNT(*) FROM all_families WHERE family_id LIKE '{year}_%'").fetchone()[0]
        logger.info(f"  -> Extracted {count:,} census families from {year}.")

    total = con.execute("SELECT COUNT(*) FROM all_families").fetchone()[0]
    logger.info(f"  -> Step 2 complete. Loaded {total:,} total families into Time Machine framework.")


def step_3_build_clan_database(con, logger):
    """
    Groups families by their exact SNAPSHOT hash to prevent clone merging!
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 3: ISOLATING UNIQUE FAMILY SNAPSHOTS...")
    logger.info("=====================================================================")

    con.execute("DROP TABLE IF EXISTS main.clan_mapping;")
    # Assign a unique ID to every exact snapshot so families with identical parents aren't merged
    con.execute("""
                CREATE TABLE main.clan_mapping AS
                SELECT DENSE_RANK() OVER (ORDER BY snapshot_fam_hash) AS clan_id, family_id, snapshot_fam_hash
                FROM temp.all_families;
                """)

    clan_count = con.execute("SELECT COUNT(DISTINCT clan_id) FROM main.clan_mapping").fetchone()[0]
    family_count = con.execute("SELECT COUNT(*) FROM main.clan_mapping").fetchone()[0]
    logger.info(f"  -> Identified {clan_count:,} unique Snapshots across {family_count:,} records.")
    logger.info("  -> Step 3 complete. Super-Clan Hairballs have been eliminated!")


def step_4_create_lineage_links(con, logger):
    """
    Finds connections between a person appearing as a child in one family
    and as an adult (head/spouse) in another, creating lineage links.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 4: STITCHING GENERATIONS (CHILD-TO-ADULT LINEAGE LINKS)...")
    logger.info("=====================================================================")

    con.execute("DROP TABLE IF EXISTS main.lineage_links;")
    con.execute("CREATE TABLE main.lineage_links (child_clan_id INTEGER, adult_clan_id INTEGER);")
    logger.info("  -> Step 4 temporarily bypassed for MVP.")


def step_5_consolidate_data(con, logger):
    """
    Final Step: Copy all data for matched clans from the yearly vaults
    into the Time Machine DB, making it a self-contained, portable database.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 5: CONSOLIDATING ALL LINKED DATA INTO THE TIME MACHINE")
    logger.info("=====================================================================")

    # We don't need to pass family_ids through Python anymore!
    # main.clan_mapping already contains the exact, target-filtered families.

    con.execute("DROP TABLE IF EXISTS main.tm_individuals;")
    con.execute("DROP TABLE IF EXISTS main.tm_families;")

    db_list = con.execute("SELECT database_name FROM duckdb_databases() WHERE database_name LIKE 'vault_%'").fetchall()
    if not db_list:
        logger.error("No yearly vaults are attached. Cannot determine schema for consolidation. Aborting.")
        return

    reference_vault = db_list[0][0]

    con.execute(
        f"CREATE TABLE main.tm_families AS SELECT family_id, 0 AS clan_id, year, head_histid, spouse_histid, kids_byr_sum, stateicp, countyicp FROM {reference_vault}.families WHERE 1=0;")
    con.execute(f"""
        CREATE TABLE main.tm_individuals AS 
        SELECT i.histid, i.family_id, 0 AS clan_id, CAST('' AS VARCHAR) AS snapshot_fam_hash,
               TRY_CAST(i.sex AS INTEGER) AS sex_int,
               TRY_CAST(i.birthyr AS INTEGER) AS byr_int,
               CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS bpl_int,
               CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS fbpl_int,
               CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS mbpl_int,
               f.stateicp, f.countyicp,
               i.occ1950, i.ind1950
        FROM {reference_vault}.individuals i
        JOIN {reference_vault}.families f ON i.family_id = f.family_id 
        WHERE 1=0;
    """)

    for year in range(1850, 1960, 10):
        if not con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            continue

        logger.info(f"  -> Extracting consolidated data from {year}...")
        con.execute(f"""
            INSERT INTO main.tm_families 
            SELECT f.family_id, c.clan_id, f.year, f.head_histid, f.spouse_histid, f.kids_byr_sum, f.stateicp, f.countyicp
            FROM vault_{year}.families f 
            JOIN main.clan_mapping c ON f.family_id = c.family_id;
        """)
        con.execute(f"""
            INSERT INTO main.tm_individuals
            SELECT i.histid, i.family_id, c.clan_id, c.snapshot_fam_hash,
                   TRY_CAST(i.sex AS INTEGER) AS sex_int,
                   TRY_CAST(i.birthyr AS INTEGER) AS byr_int,
                   CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS bpl_int,
                   CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS fbpl_int,
                   CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS mbpl_int,
                   f.stateicp, f.countyicp,
                   i.occ1950, i.ind1950
            FROM vault_{year}.individuals i 
            JOIN main.clan_mapping c ON i.family_id = c.family_id
            JOIN vault_{year}.families f ON i.family_id = f.family_id;
        """)

    logger.info("  -> Skipping explicit indexes (DuckDB columnar scans are natively fast enough).")

    logger.info("  -> Building Master Person Index (person_trajectories)...")
    con.execute("DROP TABLE IF EXISTS main.person_trajectories;")
    con.execute("""
                CREATE TABLE main.person_trajectories AS
                SELECT i.clan_id,
                       i.sex_int,
                       i.byr_int,
                       STRING_AGG(CAST(f.year AS VARCHAR) || ':' || i.histid, ', ' ORDER BY f.year) AS histid_trail,
                       STRING_AGG(CASE
                                      WHEN i.occ1950 IS NOT NULL AND i.occ1950 != '' THEN CAST(f.year AS VARCHAR) || ':' || i.occ1950
                                      ELSE NULL END,
                                  ', ' ORDER BY f.year)                                             AS lifetime_occ_trail,
                       STRING_AGG(CASE
                                      WHEN i.ind1950 IS NOT NULL AND i.ind1950 != '' THEN CAST(f.year AS VARCHAR) || ':' || i.ind1950
                                      ELSE NULL END,
                                  ', ' ORDER BY f.year)                                             AS lifetime_ind_trail
                FROM main.tm_individuals i
                         JOIN main.tm_families f ON i.family_id = f.family_id
                WHERE i.byr_int IS NOT NULL
                GROUP BY i.clan_id, i.sex_int, i.byr_int;
                """)

    logger.info("  -> Pre-calculating eternal 'Lifetime Kid Fingerprints' for all Clans...")
    con.execute("DROP TABLE IF EXISTS main.clan_details;")
    con.execute("""
                CREATE TABLE main.clan_details AS
                WITH base_clans AS (
                    SELECT DISTINCT clan_id, snapshot_fam_hash FROM main.clan_mapping
                ),
                clan_kids AS (
                    SELECT DISTINCT c.clan_id, i.sex_int, i.byr_int
                    FROM main.clan_mapping c
                    JOIN main.tm_individuals i ON c.family_id = i.family_id
                    JOIN main.tm_families f ON i.family_id = f.family_id
                    WHERE i.histid != f.head_histid
                      AND (f.spouse_histid IS NULL OR i.histid != f.spouse_histid)
                      AND i.byr_int IS NOT NULL
                ),
                kid_agg AS (
                    SELECT clan_id,
                           SUM(byr_int) AS lifetime_kfp,
                           STRING_AGG(CAST(byr_int AS VARCHAR), ',' ORDER BY byr_int) AS lifetime_kid_list
                    FROM clan_kids
                    GROUP BY clan_id
                ),
                clan_residences AS (
                    SELECT DISTINCT c.clan_id, f.year, f.stateicp, f.countyicp
                    FROM main.clan_mapping c
                    JOIN main.tm_families f ON c.family_id = f.family_id
                ),
                residence_agg AS (
                    SELECT clan_id,
                           STRING_AGG(CAST(year AS VARCHAR) || ':' || stateicp || '_' || countyicp, ',' ORDER BY year) AS lifetime_residence_list
                    FROM clan_residences
                    GROUP BY clan_id
                )
                SELECT b.clan_id,
                       b.snapshot_fam_hash,
                       COALESCE(k.lifetime_kfp, 0) AS lifetime_kfp,
                       k.lifetime_kid_list,
                       r.lifetime_residence_list
                FROM base_clans b
                         LEFT JOIN kid_agg k ON b.clan_id = k.clan_id
                         LEFT JOIN residence_agg r ON b.clan_id = r.clan_id;
                """)
    logger.info("\nSUCCESS! Time Machine is now a self-contained data warehouse.")


def step_6_debug_dump(con, logger):
    """
    Bypassed in V4: Since names have been fully purged from the deterministic Vault schema,
    we can no longer pull a debug dump based on a hardcoded surname string.
    """
    logger.warning("\n=====================================================================")
    logger.warning(f"STEP 6: DEBUG DUMP - SKIPPED")
    logger.warning("=====================================================================")
    logger.warning(
        "  -> Names have been purged from the V4 schema, so searching by DEBUG_SURNAME is no longer possible.")


def main():
    logger = gen_logging.setup_logging('DemographicLinker')
    logger.info("=====================================================================")
    logger.info("  V4 TIME MACHINE BUILDER - STRICT DETERMINISTIC PIPELINE")
    logger.info("=====================================================================")
    logger.info(f"Source Vaults Directory: {YEARLY_VAULT_DIR}")
    logger.info(f"Output Time Machine DB:  {MATCH_DB_PATH}")
    logger.info(f"Temp Directory:          {os.path.join(BASE_DATA_DIR, 'duckdb_temp')}")
    logger.info("=====================================================================")

    if os.path.exists(MATCH_DB_PATH):
        os.remove(MATCH_DB_PATH)
        logger.info(f"Removed old Match DB: {MATCH_DB_PATH}")

    con = duckdb.connect(database=MATCH_DB_PATH, read_only=False)
    # PRAGMA memory_limit removed: Letting DuckDB automatically scale to 80% of system RAM

    temp_dir = os.path.join(BASE_DATA_DIR, "duckdb_temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_dir_fwd = temp_dir.replace('\\', '/')
    con.execute(f"PRAGMA temp_directory='{temp_dir_fwd}';")
    con.execute("SET preserve_insertion_order=false;")

    step_1_attach_databases(con, logger)
    step_2_extract_census_data(con, logger)
    step_3_build_clan_database(con, logger)
    step_4_create_lineage_links(con, logger)
    step_5_consolidate_data(con, logger)
    step_6_debug_dump(con, logger)

    con.close()
    logger.info("\nTime Machine construction complete.")


if __name__ == '__main__':
    main()
