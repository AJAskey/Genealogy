"""
-----------------------------------
File: check_gedcom_bpls.py

Summary: Links all the unnamed YearlyVault databases together using DuckDB
         and counts the total population that falls into the specific 
         Birth Place (BPL) states found in the user's GEDCOM file.
         
Architect & Designer: Andy Askey
Coders (AI Assistants): Gemini Code Assist
-----------------------------------
"""

import glob
import os
import sys

import duckdb

# Add project root to sys.path so we can reach common_utils and gen_logging
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging
from utils.common_utils import is_bpl_match, get_bpl_prefixes, extract_state

# Configuration
if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
GEDCOM_JSON_PATH = os.path.join(project_root, "gedcom_sources", "gedcom_individuals.json")


def get_gedcom_places_from_json(logger):
    """Dynamically builds a dictionary of all unique states/countries from the GEDCOM JSON."""
    if not os.path.exists(GEDCOM_JSON_PATH):
        logger.error(f"GEDCOM JSON not found at: {GEDCOM_JSON_PATH}")
        return {}

    logger.info(f"Dynamically extracting BPL codes from {GEDCOM_JSON_PATH}...")
    import json

    unique_places = set()
    with open(GEDCOM_JSON_PATH, 'r', encoding='utf-8', errors='replace') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return {}
            
        for row in data:
            unique_places.add(extract_state(row.get('Birth Place', '')))
            unique_places.add(extract_state(row.get('Father Birth Place', '')))
            unique_places.add(extract_state(row.get('Mother Birth Place', '')))
            sp_bpls = row.get('Spouse Birth Place(s)', '').split('|')
            for sp_bpl in sp_bpls:
                unique_places.add(extract_state(sp_bpl.strip()))

    gedcom_states = {}
    for place in unique_places:
        if place:
            prefixes = get_bpl_prefixes(place)
            if prefixes:
                gedcom_states[place] = prefixes

    logger.info(f"Found {len(gedcom_states)} unique states/countries in the GEDCOM file.")
    return gedcom_states


def run_bpl_analysis(logger):
    logger.info("Starting GEDCOM BPL Population Analysis...")

    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    # Dynamically get the states from the current GEDCOM JSON file
    GEDCOM_STATES = get_gedcom_places_from_json(logger)
    if not GEDCOM_STATES:
        return

    # Look for files named YearVault_*.db in the VAULT_DIR
    vault_files = glob.glob(os.path.join(VAULT_DIR, "YearVault_*.db"))
    if not vault_files:
        logger.error(f"No YearVault databases found in {VAULT_DIR}")
        return

    # 1. Attach all databases and build the UNION ALL query dynamically
    union_queries = []
    for db_file in vault_files:
        year = os.path.basename(db_file).replace("YearVault_", "").replace(".db", "")
        alias = f"vault_{year}"

        try:
            con.execute(f"ATTACH '{db_file}' AS {alias} (TYPE SQLITE, READ_ONLY);")

            # Use DuckDB's information_schema to check for the table's existence.
            # The 'table_catalog' corresponds to the alias of the attached database.
            table_check_query = f"SELECT count(*) FROM information_schema.tables WHERE table_catalog = '{alias}' AND table_name = 'individuals'"
            table_exists = con.execute(table_check_query).fetchone()[0] > 0

            if table_exists:
                logger.info(f"  -> Attached {alias} and found 'individuals' table.")
                union_queries.append(f"SELECT bpld FROM {alias}.individuals WHERE bpld IS NOT NULL AND bpld != ''")
            else:
                logger.warning(f"  -> Attached {alias} but 'individuals' table was NOT FOUND. Skipping.")

        except Exception as e:
            logger.error(f"  -> Error processing {db_file}: {e}")

    if not union_queries:
        logger.error(f"No valid 'individuals' tables found in any YearVault databases to analyze in {VAULT_DIR}")
        return

    logger.info("\nExecuting massive cross-decade aggregation via DuckDB...")

    # This tells DuckDB to stack all individuals from all databases and just count the unique BPLDs
    full_query = f"""
        SELECT bpld, COUNT(*) as pop_count
        FROM ({' UNION ALL '.join(union_queries)})
        GROUP BY bpld
    """

    try:
        results = con.execute(full_query).fetchall()
        logger.info(f"Aggregation complete. Found {len(results):,} unique BPLD codes across all decades.\n")
    except Exception as e:
        logger.error(f"Error during DuckDB execution: {e}")
        return

    # 2. Map the results back to the GEDCOM states using Python
    total_population = 0
    gedcom_population = 0
    state_counts = {state: 0 for state in GEDCOM_STATES}

    for bpld, count in results:
        total_population += count
        matched = False
        for state, prefixes in GEDCOM_STATES.items():
            if is_bpl_match(bpld, prefixes):
                state_counts[state] += count
                gedcom_population += count
                matched = True
                break

    # 3. Print the Report!
    logger.info("=" * 50)
    logger.info("   GEDCOM BPL POPULATION COVERAGE REPORT")
    logger.info("=" * 50)
    logger.info(f"Total Census Individuals Analyzed: {total_population:,}")

    if total_population > 0:
        percentage = (gedcom_population / total_population) * 100
    else:
        percentage = 0.0

    logger.info(f"Individuals matching GEDCOM BPLs : {gedcom_population:,} ({percentage:.2f}%)")
    logger.info(f"Individuals OUTSIDE GEDCOM BPLs  : {total_population - gedcom_population:,}\n")

    logger.info("--- Top GEDCOM States by Census Population ---")
    sorted_states = sorted(state_counts.items(), key=lambda item: item[1], reverse=True)
    for state, count in sorted_states:
        if count > 0:
            logger.info(f"  {state.ljust(25)} | {count:,}")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging("BPL_ANALYSIS")
    run_bpl_analysis(main_logger)
