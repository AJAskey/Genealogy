"""
-----------------------------------
File: LinkFamiliesByDemographics.py
Summary: The V3 Time Machine Builder.
         Connects to all yearly census vaults, uses GEDCOM JSON targets
         to extract only relevant candidate families (Target-Driven),
         groups them into Clans, stitches child/adult records together,
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

# Add the 'python' directory and project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
MATCH_DB_PATH = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")
JSON_PATH = os.path.join(project_root, "JSON", "gedcom_couples.json")
DEBUG_SURNAME = None  # "BOSSELSTINK"  # Set to your anonymized surname for the debug dump!

NAME_TO_BPL = {
    "ALABAMA": 1, "ALASKA": 2, "ARIZONA": 4, "ARKANSAS": 5, "CALIFORNIA": 6,
    "COLORADO": 8, "CONNECTICUT": 9, "DELAWARE": 10, "DISTRICT OF COLUMBIA": 11,
    "FLORIDA": 12, "GEORGIA": 13, "HAWAII": 15, "IDAHO": 16, "ILLINOIS": 17,
    "INDIANA": 18, "IOWA": 19, "KANSAS": 20, "KENTUCKY": 21, "LOUISIANA": 22,
    "MAINE": 23, "MARYLAND": 24, "MASSACHUSETTS": 25, "MICHIGAN": 26,
    "MINNESOTA": 27, "MISSISSIPPI": 28, "MISSOURI": 29, "MONTANA": 30,
    "NEBRASKA": 31, "NEVADA": 32, "NEW HAMPSHIRE": 33, "NEW JERSEY": 34,
    "NEW MEXICO": 35, "NEW YORK": 36, "NORTH CAROLINA": 37, "NORTH DAKOTA": 38,
    "OHIO": 39, "OKLAHOMA": 40, "OREGON": 41, "PENNSYLVANIA": 42,
    "RHODE ISLAND": 44, "SOUTH CAROLINA": 45, "SOUTH DAKOTA": 46, "TENNESSEE": 47,
    "TEXAS": 48, "UTAH": 49, "VERMONT": 50, "VIRGINIA": 51, "WASHINGTON": 53,
    "WEST VIRGINIA": 54, "WISCONSIN": 55, "WYOMING": 56,
    "CANADA": 150, "MEXICO": 200, "DENMARK": 400, "NORWAY": 401, "SWEDEN": 404,
    "ENGLAND": 410, "WALES": 411, "SCOTLAND": 412, "NORTHERN IRELAND": 413, "IRELAND": 414,
    "FRANCE": 421, "NETHERLANDS": 425, "SWITZERLAND": 426, "GERMANY": 453,
    "JAPAN": 501, "SOUTH Korea": 502
}


def get_base_code(code_str):
    if not code_str: return 0
    try:
        val = int(float(code_str))
        return val // 100 if val >= 1000 else val
    except (ValueError, TypeError):
        clean_str = str(code_str).strip().upper()
        if clean_str in NAME_TO_BPL:
            return NAME_TO_BPL[clean_str]
        return 0


# ==============================================================================

def step_1_attach_databases(con, logger):
    """Attaches all yearly SQLite vaults to the in-memory DuckDB instance."""
    logger.info("STEP 1: ATTACHING ALL YEARLY VAULTS...")
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


def step_2_target_driven_extraction(con, logger):
    """
    Uses the JSON targets as a strict filter to extract ONLY relevant families
    from the 590 million census rows, preventing RAM Out-Of-Memory crashes!
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 2: TARGET-DRIVEN EXTRACTION (PULLING RELEVANT DATA INTO RAM)...")
    logger.info("=====================================================================")

    if not os.path.exists(JSON_PATH):
        logger.error(f"CRITICAL: Cannot find JSON file at {JSON_PATH}. Aborting.")
        sys.exit(1)

    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    con.execute(
        "CREATE TEMP TABLE mem_targets (h_byr_min INTEGER, h_byr_max INTEGER, h_bpl INTEGER, w_byr_min INTEGER, w_byr_max INTEGER, w_bpl INTEGER)")

    targets_inserted = 0
    for couple in data:
        h_byr = couple.get('h_byr')
        w_byr = couple.get('w_byr')
        if not h_byr or not w_byr or not str(h_byr).isnumeric() or not str(w_byr).isnumeric():
            continue

        h_bpl = get_base_code(couple.get('h_bpl'))
        w_bpl = get_base_code(couple.get('w_bpl'))
        h_fbpl = get_base_code(couple.get('h_fbpl'))
        h_mbpl = get_base_code(couple.get('h_mbpl'))
        w_fbpl = get_base_code(couple.get('w_fbpl'))
        w_mbpl = get_base_code(couple.get('w_mbpl'))

        # Skip couples missing core demographics, but allow missing parents so we cast a wide net into the Time Machine!
        if 0 in (h_bpl, w_bpl):
            continue

        h_byr_int = int(h_byr)
        w_byr_int = int(w_byr)

        # Insert target with a +/- 5 year age drift window
        con.execute("INSERT INTO mem_targets VALUES (?, ?, ?, ?, ?, ?)",
                    (h_byr_int - 5, h_byr_int + 5, h_bpl, w_byr_int - 5, w_byr_int + 5, w_bpl))
        targets_inserted += 1

    logger.info(f"  -> Loaded {targets_inserted:,} fully-documented target couples into RAM filter.")

    con.execute("""
        CREATE TEMP TABLE all_individuals AS 
        SELECT histid, family_id, first_name, last_name, sex, birthyr, bpld, fbpl, mbpl 
        FROM vault_1850.individuals WHERE 1=0;
    """)
    con.execute("""
        CREATE TEMP TABLE all_families AS 
        SELECT family_id, head_histid, spouse_histid 
        FROM vault_1850.families WHERE 1=0;
    """)

    for year in range(1850, 1960, 10):
        if not con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            continue

        # Force a sequential bulk-read into DuckDB RAM to completely bypass slow SQLite index lookups
        con.execute(f"""
            CREATE TEMP TABLE local_fams AS SELECT family_id, head_histid, spouse_histid FROM vault_{year}.families;
            CREATE TEMP TABLE local_inds AS SELECT histid, family_id, first_name, last_name, sex, birthyr, bpld, fbpl, mbpl FROM vault_{year}.individuals;
        """)

        # Extract only the families that mathematically match our target filters
        con.execute(f"""
            INSERT INTO all_families
            SELECT DISTINCT f.family_id, f.head_histid, f.spouse_histid
            FROM local_fams f
            JOIN local_inds h ON f.head_histid = h.histid
            JOIN local_inds s ON f.spouse_histid = s.histid
            JOIN mem_targets t ON 
                TRY_CAST(h.birthyr AS INTEGER) BETWEEN t.h_byr_min AND t.h_byr_max
                AND TRY_CAST(s.birthyr AS INTEGER) BETWEEN t.w_byr_min AND t.w_byr_max
                AND h.sex = '1' AND s.sex = '2'
                AND (CASE WHEN TRY_CAST(h.bpld AS INTEGER) >= 1000 THEN TRY_CAST(h.bpld AS INTEGER)//100 ELSE TRY_CAST(h.bpld AS INTEGER) END) = t.h_bpl
                AND (CASE WHEN TRY_CAST(s.bpld AS INTEGER) >= 1000 THEN TRY_CAST(s.bpld AS INTEGER)//100 ELSE TRY_CAST(s.bpld AS INTEGER) END) = t.w_bpl;
        """)

        # Pull the individuals for those matched families
        con.execute(f"""
            INSERT INTO all_individuals
            SELECT i.* FROM local_inds i
            JOIN all_families af ON i.family_id = af.family_id
            WHERE i.family_id LIKE '{year}_%';
        """)

        # Drop the local tables to free memory for the next decade
        con.execute("DROP TABLE local_fams;")
        con.execute("DROP TABLE local_inds;")

        count = con.execute(f"SELECT COUNT(*) FROM all_individuals WHERE family_id LIKE '{year}_%'").fetchone()[0]
        logger.info(f"  -> Extracted {count:,} highly relevant individuals from {year}.")

    total = con.execute("SELECT COUNT(*) FROM all_individuals").fetchone()[0]
    logger.info(f"  -> Step 2 complete. Reduced processing pool down to {total:,} total individuals.")


def step_3_identify_multi_decade_individuals(con, logger):
    """
    Identifies individuals who appear in more than one census decade
    by creating a unique demographic hash for each person.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 3: IDENTIFYING INDIVIDUALS ACROSS MULTIPLE DECADES...")
    logger.info("=====================================================================")

    # DECISION: We DO NOT use names in the dem_hash because they are blank/scrambled.
    # We rely purely on Birth Year, Sex, Base BPL, and Parent BPLs to track people across decades.
    con.execute("""
                CREATE
                TEMP TABLE dem_hashes AS
                SELECT trim(cast(birthyr as varchar)) || '|' || trim(cast(sex as varchar)) || '|' ||
                       cast(CASE
                                WHEN TRY_CAST(bpld AS INTEGER) >= 1000 THEN TRY_CAST(bpld AS INTEGER) // 100
                                ELSE TRY_CAST(bpld AS INTEGER) END as varchar) || '|' ||
                       COALESCE(cast(CASE
                                         WHEN TRY_CAST(fbpl AS INTEGER) >= 1000 THEN TRY_CAST(fbpl AS INTEGER) // 100
                                         ELSE TRY_CAST(fbpl AS INTEGER) END as varchar), '0') || '|' ||
                       COALESCE(cast(CASE
                                         WHEN TRY_CAST(mbpl AS INTEGER) >= 1000 THEN TRY_CAST(mbpl AS INTEGER) // 100
                                         ELSE TRY_CAST(mbpl AS INTEGER) END as varchar), '0') as dem_hash,
                       histid,
                       family_id
                FROM temp.all_individuals;
                """)

    logger.info("  -> Step 3 complete. Demographic hashes created.")


def step_4_build_clan_database(con, logger):
    """
    Groups families into 'clans' by enforcing the Dual-Key Lock (Head + Spouse).
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 4: BUILDING CLANS VIA DUAL-KEY LOCK...")
    logger.info("=====================================================================")

    # Create a family hash by combining Head and Spouse demographic hashes
    con.execute("""
                CREATE
                TEMP TABLE family_hashes AS
                SELECT f.family_id,
                       h.dem_hash || '-SP-' || COALESCE(s.dem_hash, 'NONE') AS family_hash
                FROM temp.all_families f
                         JOIN temp.dem_hashes h ON f.head_histid = h.histid
                         LEFT JOIN temp.dem_hashes s ON f.spouse_histid = s.histid;
                """)

    con.execute("DROP TABLE IF EXISTS main.clan_mapping;")
    # DENSE_RANK assigns a unique integer ID to each unique Dual-Key family hash!
    con.execute("""
                CREATE TABLE main.clan_mapping AS
                SELECT DENSE_RANK() OVER (ORDER BY family_hash) AS clan_id, family_id
                FROM temp.family_hashes;
                """)

    clan_count = con.execute("SELECT COUNT(DISTINCT clan_id) FROM main.clan_mapping").fetchone()[0]
    family_count = con.execute("SELECT COUNT(*) FROM main.clan_mapping").fetchone()[0]
    logger.info(f"  -> Identified {clan_count:,} distinct Dual-Key Clans containing {family_count:,} total families.")
    logger.info("  -> Step 4 complete. The Hairball has been eliminated!")


def step_5_create_lineage_links(con, logger):
    """
    Finds connections between a person appearing as a child in one family
    and as an adult (head/spouse) in another, creating lineage links.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 5: STITCHING GENERATIONS (CHILD-TO-ADULT LINEAGE LINKS)...")
    logger.info("=====================================================================")

    con.execute("DROP TABLE IF EXISTS main.lineage_links;")
    con.execute("CREATE TABLE main.lineage_links (child_clan_id INTEGER, adult_clan_id INTEGER);")

    logger.info("  -> Step 5 temporarily bypassed for MVP.")
    logger.info(
        "  -> (Joining purely on dem_hash creates a massive Cartesian explosion. We will tackle lineage linking later!)")


def step_6_consolidate_data(con, logger):
    """
    Final Step: Copy all data for matched clans from the yearly vaults
    into the Time Machine DB, making it a self-contained, portable database.
    """
    logger.info("\n=====================================================================")
    logger.info("STEP 6: CONSOLIDATING ALL LINKED DATA INTO THE TIME MACHINE")
    logger.info("=====================================================================")

    family_ids_query = con.execute("SELECT DISTINCT family_id FROM temp.all_families")
    if not family_ids_query:
        logger.warning("No families found in target extraction. Skipping consolidation.")
        return

    family_ids = [f[0] for f in family_ids_query.fetchall()]
    if not family_ids:
        logger.warning("No families found in target extraction. Skipping consolidation.")
        return

    # Create the final tables in the Time Machine DB
    con.execute("DROP TABLE IF EXISTS main.tm_individuals;")
    con.execute("DROP TABLE IF EXISTS main.tm_families;")

    # Need a reference schema. Check which vault is attached.
    db_list = con.execute("SELECT database_name FROM duckdb_databases() WHERE database_name LIKE 'vault_%'").fetchall()
    if not db_list:
        logger.error("No yearly vaults are attached. Cannot determine schema for consolidation. Aborting Step 6.")
        return

    reference_vault = db_list[0][0]  # Use the first available vault for schema

    # Fixed syntax to safely copy schema without using LIKE on attached databases
    con.execute(
        f"CREATE TABLE main.tm_families AS SELECT family_id, year, head_histid, spouse_histid, kids_byr_sum, stateicp, countyicp FROM {reference_vault}.families WHERE 1=0;")
    con.execute(f"""
        CREATE TABLE main.tm_individuals AS 
        SELECT i.histid, i.family_id, i.first_name, i.last_name, i.sex,
               TRY_CAST(i.birthyr AS INTEGER) AS byr_int,
               CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS bpl_int,
               CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS fbpl_int,
               CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS mbpl_int,
               f.stateicp, f.countyicp
        FROM {reference_vault}.individuals i
        JOIN {reference_vault}.families f ON i.family_id = f.family_id 
        WHERE 1=0;
    """)

    # Create a temporary table of all target family IDs for hyper-efficient joining
    con.execute("CREATE TEMP TABLE temp_fids AS SELECT unnest(?) AS column0", [family_ids])

    for year in range(1850, 1960, 10):
        # Check if the vault for this year is actually attached
        if not con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            continue

        logger.info(f"  -> Extracting consolidated data from {year}...")

        # Use the temp table for efficient joins
        con.execute(f"""
            INSERT INTO main.tm_families 
            SELECT f.family_id, f.year, f.head_histid, f.spouse_histid, f.kids_byr_sum, f.stateicp, f.countyicp
            FROM vault_{year}.families f JOIN temp_fids tf ON f.family_id = tf.column0;
        """)
        con.execute(f"""
            INSERT INTO main.tm_individuals
            SELECT i.histid, i.family_id, i.first_name, i.last_name, i.sex,
                   TRY_CAST(i.birthyr AS INTEGER) AS byr_int,
                   CASE WHEN TRY_CAST(i.bpld AS INTEGER) >= 1000 THEN TRY_CAST(i.bpld AS INTEGER) // 100 ELSE TRY_CAST(i.bpld AS INTEGER) END AS bpl_int,
                   CASE WHEN TRY_CAST(i.fbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.fbpl AS INTEGER) // 100 ELSE TRY_CAST(i.fbpl AS INTEGER) END AS fbpl_int,
                   CASE WHEN TRY_CAST(i.mbpl AS INTEGER) >= 1000 THEN TRY_CAST(i.mbpl AS INTEGER) // 100 ELSE TRY_CAST(i.mbpl AS INTEGER) END AS mbpl_int,
                   f.stateicp, f.countyicp
            FROM vault_{year}.individuals i 
            JOIN temp_fids tf ON i.family_id = tf.column0
            JOIN vault_{year}.families f ON i.family_id = f.family_id;
        """)

    logger.info("  -> Building high-performance indexes on Demographics Database...")
    con.execute("CREATE INDEX idx_tm_inds_histid ON main.tm_individuals(histid);")
    con.execute("CREATE INDEX idx_tm_inds_famid ON main.tm_individuals(family_id);")
    con.execute("CREATE INDEX idx_tm_fams_famid ON main.tm_families(family_id);")
    con.execute("CREATE INDEX idx_tm_inds_byr ON main.tm_individuals(byr_int);")

    logger.info("  -> Pre-calculating eternal 'Lifetime Kid Fingerprints' for all Clans...")
    con.execute("DROP TABLE IF EXISTS main.clan_details;")
    con.execute("""
                CREATE TABLE main.clan_details AS
                WITH clan_kids AS (SELECT DISTINCT c.clan_id,
                                                   i.sex,
                                                   i.byr_int
                                   FROM main.clan_mapping c
                                            JOIN main.tm_individuals i ON c.family_id = i.family_id
                                            JOIN main.tm_families f ON i.family_id = f.family_id
                                   WHERE i.histid != f.head_histid
                    AND
                (
                    f
                    .
                    spouse_histid
                    IS
                    NULL
                    OR
                    i
                    .
                    histid
                    !=
                    f
                    .
                    spouse_histid
                )
                    AND i.byr_int IS NOT NULL
                    )
                SELECT clan_id, 
                       SUM(byr_int) AS lifetime_kfp,
                       STRING_AGG(CAST(byr_int AS VARCHAR), ',' ORDER BY byr_int) AS lifetime_kid_list
                FROM clan_kids
                GROUP BY clan_id;
                """)

    logger.info("\nSUCCESS! Time Machine is now a self-contained data warehouse.")


def step_7_debug_dump(con, logger):
    """
    Dumps the GEDCOM targets and all raw census data for a specific surname
    into the Time Machine DB so you can manually inspect and debug rejections.
    """
    if not DEBUG_SURNAME:
        return

    logger.info("\n=====================================================================")
    logger.info(f"STEP 7: DEBUG DUMP - SAVING GEDCOM TARGETS & '{DEBUG_SURNAME}' CENSUS DATA")
    logger.info("=====================================================================")

    con.execute("DROP TABLE IF EXISTS main.debug_individuals;")
    con.execute("DROP TABLE IF EXISTS main.debug_families;")
    con.execute("DROP TABLE IF EXISTS main.gedcom_targets;")

    # 1. Save the JSON targets into the database
    if os.path.exists(JSON_PATH):
        logger.info("  -> Loading GEDCOM JSON targets into main.gedcom_targets...")
        # Normalize path for DuckDB
        json_path_fwd = JSON_PATH.replace('\\', '/')
        con.execute(f"CREATE TABLE main.gedcom_targets AS SELECT * FROM read_json_auto('{json_path_fwd}');")
        count = con.execute("SELECT COUNT(*) FROM main.gedcom_targets").fetchone()[0]
        logger.info(f"  -> Saved {count} GEDCOM targets.")
    else:
        logger.warning(f"  -> JSON file not found at {JSON_PATH}. Skipping gedcom_targets.")

    # 2. Extract all Census data for the target surname
    logger.info(f"  -> Gathering all individuals with last name like '{DEBUG_SURNAME}%' from raw vaults...")

    # Safely copy schema into memory temp table
    con.execute("CREATE TEMP TABLE debug_inds_temp AS SELECT * FROM main.tm_individuals WHERE 1=0;")
    for year in range(1850, 1960, 10):
        if con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            con.execute(
                f"INSERT INTO debug_inds_temp SELECT * FROM vault_{year}.individuals WHERE upper(last_name) LIKE upper('{DEBUG_SURNAME}%');")

    con.execute("CREATE TABLE main.debug_individuals AS SELECT * FROM debug_inds_temp;")

    logger.info("  -> Gathering their full households...")
    con.execute("CREATE TEMP TABLE debug_fams_temp AS SELECT * FROM main.tm_families WHERE 1=0;")
    for year in range(1850, 1960, 10):
        if con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            con.execute(
                f"INSERT INTO debug_fams_temp SELECT * FROM vault_{year}.families WHERE family_id IN (SELECT family_id FROM main.debug_individuals);")

    con.execute("CREATE TABLE main.debug_families AS SELECT * FROM debug_fams_temp;")

    # Now pull the rest of the household members who might have different last names
    for year in range(1850, 1960, 10):
        if con.execute(f"SELECT 1 FROM duckdb_databases() WHERE database_name = 'vault_{year}'").fetchone():
            con.execute(f"""
                INSERT INTO main.debug_individuals
                SELECT i.* FROM vault_{year}.individuals i
                JOIN main.debug_families f ON i.family_id = f.family_id
                WHERE i.histid NOT IN (SELECT histid FROM main.debug_individuals);
            """)

    total_inds = con.execute("SELECT COUNT(*) FROM main.debug_individuals").fetchone()[0]
    logger.info(f"  -> Added household members. Total debug individuals saved: {total_inds:,}.")
    logger.info("  -> DEBUG DUMP COMPLETE! Open DemographicMatches.db to view the data.")


def main():
    logger = gen_logging.setup_logging('DemographicLinker')
    logger.info("=====================================================================")
    logger.info("  V3 TIME MACHINE BUILDER - LINKING FAMILIES BY DEMOGRAPHICS")
    logger.info("=====================================================================")

    if os.path.exists(MATCH_DB_PATH):
        os.remove(MATCH_DB_PATH)
        logger.info(f"Removed old Match DB: {MATCH_DB_PATH}")

    con = duckdb.connect(database=MATCH_DB_PATH, read_only=False)
    con.execute("PRAGMA memory_limit='32GB';")

    # Allow DuckDB to spill to disk if memory is exceeded
    temp_dir = os.path.join(BASE_DATA_DIR, "duckdb_temp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_dir_fwd = temp_dir.replace('\\', '/')
    con.execute(f"PRAGMA temp_directory='{temp_dir_fwd}';")
    con.execute("SET preserve_insertion_order=false;")

    step_1_attach_databases(con, logger)
    step_2_target_driven_extraction(con, logger)
    step_3_identify_multi_decade_individuals(con, logger)
    step_4_build_clan_database(con, logger)
    step_5_create_lineage_links(con, logger)
    step_6_consolidate_data(con, logger)

    con.close()
    logger.info("\nTime Machine construction complete.")


if __name__ == '__main__':
    main()
