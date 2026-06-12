"""
-----------------------------------
File: GedcomNameOverlay.py

Summary: The "Label-Maker" for the Census-First Architecture.
         This script takes auxiliary CSV files, extracts
         the demographic fingerprints of the individuals within, and uses
         them to find and "paint" names onto the nameless, mathematically
         proven family structures in our Master Relational Vault.

Design:
  - Step 1: Prepare the Named Vault by copying the Master Relational Vault.
  - Step 2: Parse CSV files to extract Individuals (Names, Sex, BirthYr, BPL, FBPL, MBPL).
  - Step 3: Search the MasterVault_Relational.db for an exact matching
            individual based on Sex, Birth Year (+/- 2), and the 3 Birthplaces.
            Uses the DemographicMatches.db 'clan_mapping' to handle Time Machine Echoes.
  - Step 4: If a unique match is found, update the "Future Bosselstink"
            placeholders in the 'individuals' table with the correct
            historical names from the CSV.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import csv
import os
import shutil
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

# The database we are reading from (our ground truth)
MASTER_DB = os.path.join(BASE_DATA_DIR, "MasterVault_Relational.db")

# The database we are writing the name changes to.
# DECISION: We create a NEW database for the overlay. This keeps our raw
# relational vault immutable. The final export will join this overlay
# with the master vault to get the complete picture.
NAMED_DB = os.path.join(BASE_DATA_DIR, "MasterVault_Named.db")

MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")

# A directory where you can drop all your CSV files
GEDCOM_INPUT_DIR = os.path.join(project_root, "gedcom_sources")


def get_bpl_prefixes(birth_place):
    """
    Translates a free-text string (like 'Centre County, Pennsylvania, USA')
    into the standard IPUMS 1-to-3 digit BPL prefix.
    """
    if not birth_place:
        return None

    bp_lower = birth_place.lower()

    # Standard IPUMS BPL codes for US States and common Foreign Countries
    crosswalk = {
        "alabama": ["01", "1"], "alaska": ["02", "2"], "arizona": ["04", "4"], "arkansas": ["05", "5"],
        "california": ["06", "6"], "colorado": ["08", "8"], "connecticut": ["09", "9"],
        "delaware": ["10"], "district of columbia": ["11"], "florida": ["12"],
        "georgia": ["13"], "hawaii": ["15"], "idaho": ["16"], "illinois": ["17"],
        "indiana": ["18"], "iowa": ["19"], "kansas": ["20"], "kentucky": ["21"],
        "louisiana": ["22"], "maine": ["23"], "maryland": ["24"], "massachusetts": ["25"],
        "michigan": ["26"], "minnesota": ["27"], "mississippi": ["28"], "missouri": ["29"],
        "montana": ["30"], "nebraska": ["31"], "nevada": ["32"], "new hampshire": ["33"],
        "new jersey": ["34"], "new mexico": ["35"], "new york": ["36"], "north carolina": ["37"],
        "north dakota": ["38"], "ohio": ["39"], "oklahoma": ["40"], "oregon": ["41"],
        "pennsylvania": ["42", "042"], "rhode island": ["44", "044"], "south carolina": ["45", "045"],
        "south dakota": ["46", "046"], "tennessee": ["47", "047"], "texas": ["48", "048"],
        "utah": ["49", "049"], "vermont": ["50", "050"], "virginia": ["51", "051"],
        "washington": ["53", "053"], "west virginia": ["54", "054"], "wisconsin": ["55", "055"],
        "wyoming": ["56", "056"],

        "england": ["410"], "scotland": ["411"], "wales": ["412"],
        "ireland": ["414"], "northern ireland": ["414"],
        "germany": ["453"], "sweden": ["404"], "norway": ["401"],
        "denmark": ["400"], "netherlands": ["425"], "france": ["421"],
        "switzerland": ["426"], "canada": ["150"], "mexico": ["200"],
        "japan": ["501"], "south korea": ["502"], "korea": ["502"]
    }

    for state, prefixes in crosswalk.items():
        if state in bp_lower:
            return prefixes

    return None


def parse_csv_names_and_dates(filepath):
    """
    Reads the CSV file exported from our utils script.
    Extracts Individuals and their 3 Location Anchors (BPL, FBPL, MBPL).
    """
    target_individuals = []

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            first_name = row.get('first_name', '').strip()
            last_name = row.get('last_name', '').strip()
            sex = row.get('sex', '').strip()
            birth_year = row.get('birth_year', '').strip()

            # DECISION: Automatically skip Ancestry placeholders like "--" or "Hidden"
            if '--' in first_name or '--' in last_name or 'Hidden' in first_name or 'Hidden' in last_name:
                continue

            if first_name and last_name and sex and birth_year:
                try:
                    byr_int = int(birth_year)

                    # DECISION: User requested to skip anyone born before 1850
                    if byr_int < 1850:
                        continue

                    target_individuals.append({
                        'first_name': first_name,
                        'last_name': last_name,
                        'sex': sex,
                        'birthyr': byr_int,
                        'bpld': row.get('birth_place', '').strip(),
                        'fbpl': row.get('father_birth_place', '').strip(),
                        'mbpl': row.get('mother_birth_place', '').strip()
                    })
                except ValueError:
                    pass

    return target_individuals


def apply_gedcom_names(logger):
    """
    Finds nameless families in the Master Vault that match the demographic
    fingerprint of families in the auxiliary CSV files and applies the
    correct historical names.
    """
    logger.info("Step 1/4: Preparing the 'Named' Database Vault...")
    if not os.path.exists(NAMED_DB):
        logger.info(f"  -> Copying {MASTER_DB} to {NAMED_DB} to protect raw data...")
        shutil.copy2(MASTER_DB, NAMED_DB)
    else:
        logger.info(f"  -> {NAMED_DB} already exists. Using existing file.")

    # --------------------------------------------------------------------------
    # Step 2: Parse CSV files
    # --------------------------------------------------------------------------
    logger.info(f"\nStep 2/4: Scanning for CSV files in: {GEDCOM_INPUT_DIR}")
    os.makedirs(GEDCOM_INPUT_DIR, exist_ok=True)

    csv_files = [f for f in os.listdir(GEDCOM_INPUT_DIR) if f.lower().endswith('.csv')]
    if not csv_files:
        logger.warning("  -> No .csv files found! Please drop your exported CSVs in the folder and rerun.")
        return

    all_target_individuals = []

    for file in csv_files:
        filepath = os.path.join(GEDCOM_INPUT_DIR, file)
        individuals = parse_csv_names_and_dates(filepath)
        all_target_individuals.extend(individuals)
        logger.info(f"  -> Extracted {len(individuals)} individuals with complete demographics from {file}")

    # --------------------------------------------------------------------------
    # Step 3: Perform the SQL Lookup
    # --------------------------------------------------------------------------
    logger.info("\nStep 3/4: Searching for nameless individuals in the Named Vault...")

    update_queue = []
    multiple_count = 0
    too_many_count = 0
    clans_to_update = {}
    zero_count = 0
    success_count = 0
    flagged_multiples = set()

    # DECISION: Load ONLY the 'Future Bosselstink' records into Python memory.
    # This essentially builds an instantaneous, in-memory Hash Join.
    logger.info("  -> Fetching all Bosselstinks into memory...")
    with (sqlite3.connect(NAMED_DB) as sqlite_conn):
        sqlite_cursor = sqlite_conn.cursor()

        # DECISION: We load the Clan Mappings from the Time Machine to solve the "Time Machine Echo".
        logger.info("  -> Loading Clan Mappings from the Time Machine...")
        try:
            sqlite_cursor.execute(f"ATTACH DATABASE '{MATCH_DB}' AS match_db")
            sqlite_cursor.execute("SELECT family_id, clan_id FROM match_db.clan_mapping")
            clan_map = {row[0]: row[1] for row in sqlite_cursor.fetchall()}
            sqlite_cursor.execute("DETACH DATABASE match_db")
            logger.info(f"  -> Loaded {len(clan_map):,} family-to-clan links.")
        except sqlite3.OperationalError:
            logger.warning("  -> MATCH_DB not found! Clan consolidation disabled.")
            clan_map = {}

        sqlite_cursor.execute("""
                              SELECT histid, family_id, sex, birthyr, bpld, fbpl, mbpl
                              FROM individuals
                              WHERE last_name = 'Bosselstink'
                                AND first_name = 'Future'
                                AND birthyr IS NOT NULL
                              """)
        bosselstinks = sqlite_cursor.fetchall()
        logger.info(f"  -> Found {len(bosselstinks):,} Bosselstinks. Building memory index...")

        # Build the memory index keyed by (sex, birthyr)
        mem_index = {}
        for row in bosselstinks:
            key = (row[2], row[3])
            if key not in mem_index:
                mem_index[key] = []
            mem_index[key].append(row)

        logger.info("  -> Matching individuals against memory index...")

        for ind in all_target_individuals:
            target_sex = ind['sex']
            target_byr = ind['birthyr']

            bpl_prefixes = get_bpl_prefixes(ind['bpld'])
            fbpl_prefixes = get_bpl_prefixes(ind['fbpl'])
            mbpl_prefixes = get_bpl_prefixes(ind['mbpl'])

            # Hunt for matches in the +/- 2 year window
            results = []
            for offset in range(-2, 3):
                key = (target_sex, target_byr + offset)
                if key in mem_index:
                    for db_row in mem_index[key]:
                        histid, fam_id, db_sex, db_byr, db_bpld, db_fbpl, db_mbpl = db_row

                        # DECISION: STRICT ENFORCEMENT. If the CSV has a parent birthplace,
                        # the DB *must* have it and it must match.
                        if bpl_prefixes:
                            if not db_bpld or not any(str(db_bpld).startswith(p) for p in bpl_prefixes): continue
                        if fbpl_prefixes:
                            if not db_fbpl or not any(str(db_fbpl).startswith(p) for p in fbpl_prefixes): continue
                        if mbpl_prefixes:
                            if not db_mbpl or not any(str(db_mbpl).startswith(p) for p in mbpl_prefixes): continue

                        logger.info(f"\n\tappend db_row:{db_row} \n")
                        logger.info(
                            f"\tbpl_prefixes:{bpl_prefixes} mbpl_prefixes:{mbpl_prefixes}   fbpl_prefixes:{fbpl_prefixes} \n")

                        results.append(db_row)

            # Resolve the "Time Machine Echo" using Clans
            unique_clans = set()
            unclanned_individuals = set()
            for db_row in results:
                histid = db_row[0]
                fam_id = db_row[1]
                clan_id = clan_map.get(fam_id)
                if clan_id:
                    unique_clans.add(clan_id)
                else:
                    unclanned_individuals.add(histid)

            total_unique_entities = len(unique_clans) + len(unclanned_individuals)

            if total_unique_entities == 1:
                # SUCCESS!
                success_count += 1

                # DECISION: "The Anchor Strategy". Because 1850-1870 censuses lack parent birthplaces,
                # our strict filter safely rejected them. BUT if we found a perfect 1880+ anchor,
                # we can use the Clan ID to ripple the name backwards in time to those early records!
                if len(unique_clans) == 1:
                    target_clan = list(unique_clans)[0]
                    clans_to_update[target_clan] = (ind['first_name'], ind['last_name'])
                else:
                    target_histid = list(unclanned_individuals)[0]
                    update_queue.append((ind['first_name'], ind['last_name'], target_histid))

            elif total_unique_entities > 1:
                # DECISION: Protect the database! If we get hundreds of thousands of hits
                # because the CSV lacked parent birthplaces, we DO NOT want to overwrite all of them.
                if total_unique_entities > 20:
                    logger.warning(
                        f"  [TOO MANY] Found {total_unique_entities:,} distinct families for {ind['first_name']} {ind['last_name']} ({ind['birthyr']}). Not enough CSV data to isolate. Skipping.")
                    too_many_count += 1
                else:
                    logger.warning(
                        f"  [MULTIPLE] Found {total_unique_entities} distinct families for {ind['first_name']} {ind['last_name']} ({ind['birthyr']}). Flagging as 'Multiple'.")
                    multiple_count += 1
                    for db_row in results:
                        histid = db_row[0]
                        if histid not in flagged_multiples:
                            update_queue.append(('Multiple', 'Bosselstink', histid))
                            flagged_multiples.add(histid)
            else:
                logger.info(
                    f"  [NONE] 0 Bosselstinks found for {ind['first_name']} {ind['last_name']} ({ind['birthyr']}).")
                zero_count += 1

    logger.info(f"\nLookup Complete:")
    logger.info(f"  -> Perfect Unique Matches: {success_count:,}")
    logger.info(f"  -> Multiple Matches Flagged (<20): {multiple_count:,}")
    logger.info(f"  -> Too Many Matches (Skipped): {too_many_count:,}")
    logger.info(f"  -> Zero Matches (Skipped): {zero_count:,}")

    if clans_to_update:
        logger.info("\n  -> Resolving 'Time Machine Echoes' across 100-year timelines (Single Pass)...")
        for row in bosselstinks:
            c_id = clan_map.get(row[1])
            if c_id and c_id in clans_to_update:
                fname, lname = clans_to_update[c_id]
                update_queue.append((fname, lname, row[0]))

    # --------------------------------------------------------------------------
    # Step 4: Update the Names
    # --------------------------------------------------------------------------
    logger.info(f"\nStep 4/4: Applying {len(update_queue)} historical names to the census records...")

    # We use standard SQLite to execute the updates directly onto the hard drive file
    with sqlite3.connect(NAMED_DB) as sqlite_conn:
        sqlite_conn.execute("PRAGMA journal_mode=WAL")
        sqlite_cursor = sqlite_conn.cursor()

        sqlite_cursor.executemany("""
                                  UPDATE individuals
                                  SET first_name = ?,
                                      last_name  = ?
                                  WHERE histid = ?
                                  """, update_queue)

        sqlite_conn.commit()

    logger.info("\nSUCCESS! CSV Name Overlay complete.")
    logger.info(f"Open '{NAMED_DB}' to see your named ancestors!")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="NAME_OVERLAY")
    apply_gedcom_names(main_logger)
