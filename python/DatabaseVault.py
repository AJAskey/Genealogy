"""
-----------------------------------
File: DatabaseVault.py

Summary: Ingests raw IPUMS data into a strictly normalized SQLite database.
         Reads the CSV sequentially, buffering households by SERIAL.
         Maps relationships using POPLOC/MOMLOC to extract exact HISTIDs
         for parents, and writes to 'families' and 'individuals' tables.

Design:  Single-threaded, sequential read.
         Assigns "Future Bosselstink" to nameless records.
         Saves the entire raw CSV row as JSON "bread crumbs" so no data is lost.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0 http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: https://github.com/AJAskey/Genealogy

--------------------------------
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# ==============================================================================
# TUNING KNOBS
# ==============================================================================
BATCH_SIZE = 100_000  # Number of *Households* to buffer before committing to DB

if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
input_directory = os.path.join(BASE_DATA_DIR, "ShortTermCSVfiles")


# ==============================================================================
# DATABASE SETUP
# ==============================================================================
def setup_database(db_path, logger):
    logger.info(f"Connecting to database (Setup): {db_path}")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # DECISION: Write-Ahead Logging (WAL) ensures that if the script is killed (Ctrl+C) mid-run,
    # the database does not corrupt. It safely rolls back incomplete transactions and allows parallel reads.
    cursor.execute("PRAGMA journal_mode=WAL")

    # DECISION: Set synchronous mode to NORMAL. In WAL mode, this provides a massive write speed boost
    # without risking database corruption, perfectly balancing our ingestion speed and safety.
    cursor.execute("PRAGMA synchronous = NORMAL;")

    # DECISION: Enforce Relational Integrity during setup.
    cursor.execute("PRAGMA foreign_keys = ON;")

    # DECISION: The Families Table represents the "Nuclear Family Unit", NOT just the physical house.
    # By tracking 'famunit', we separate multiple families living under the same roof (e.g., boarders, servants).
    # We also extract core metrics (head_histid, spouse_histid, numprec) up to the family level
    # to make downstream querying incredibly fast without needing complex JOINs.
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS families
                   (
                       family_id
                       TEXT
                       PRIMARY
                       KEY,
                       year
                       INTEGER,
                       serial
                       TEXT,
                       famunit
                       TEXT,
                       head_histid
                       TEXT,
                       spouse_histid
                       TEXT,
                       hhtype
                       TEXT,
                       numprec
                       TEXT,
                       pernum
                       TEXT,
                       eldch
                       TEXT,
                       yngch
                       TEXT,
                       relate
                       TEXT
                   )
                   ''')

    # DECISION: The Individuals Table stores the raw demographics and links to the Family Table via Foreign Key.
    # The 'raw_data' column acts as our "Bread Crumbs", storing the entire JSON row so we
    # never lose any of the 50+ IPUMS variables, even if we don't explicitly parse them into columns today.
    # HISTID is used as the Primary Key because IPUMS guarantees it is a universally unique, permanent ID.
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS individuals
                   (
                       histid
                       TEXT
                       PRIMARY
                       KEY,
                       first_name
                       TEXT,
                       last_name
                       TEXT,
                       year
                       INTEGER,
                       sample
                       TEXT,
                       serial
                       TEXT,
                       pernum
                       TEXT,
                       famunit
                       TEXT,
                       age
                       INTEGER,
                       sex
                       TEXT,
                       birthyr
                       INTEGER,
                       birthmo
                       INTEGER,
                       marrnoyrs
                       INTEGER,
                       bpld
                       TEXT,
                       fbpl
                       TEXT,
                       mbpl
                       TEXT,
                       father_histid
                       TEXT,
                       mother_histid
                       TEXT,
                       family_id
                       TEXT,
                       raw_data
                       TEXT, -- The Bread Crumbs! (JSON)
                       FOREIGN
                       KEY
                   (
                       family_id
                   ) REFERENCES families
                   (
                       family_id
                   )
                       )
                   ''')

    conn.commit()
    conn.close()


# ==============================================================================
# HOUSEHOLD PROCESSOR
# ==============================================================================
def process_household(rows):
    """
    Takes a buffer of rows for a single SERIAL number.
    Maps children to their exact parents using HISTID, and constructs the tables.
    """
    # DECISION: Create a quick lookup dictionary mapping the enumerator's line number (PERNUM)
    # to the person's permanent IPUMS UUID (HISTID). This allows us to instantly resolve POPLOC/MOMLOC pointers.
    pernum_to_histid = {str(r.get('PERNUM', '')).strip(): str(r.get('HISTID', '')).strip() for r in rows}

    families_dict = {}
    individuals_by_fam = {}

    for row in rows:
        # DECISION: HHTYPE Filter. We only want Family Households (1, 2, or 3).
        # Note: If older census years (like 1850) use '0' (N/A) for HHTYPE, those households will be skipped!
        hhtype = str(row.get('HHTYPE', '')).strip()
        if hhtype not in ('1', '2', '3'):
            continue

        # DECISION: Relatives Filter. We only want immediate/extended family (RELATE 1-9 or RELATED 100-999).
        # This excludes "Other relatives" (10 / 1000+), "Boarders/Partners" (11 / 1100+), and "Non-relatives" (12 / 1200+).
        relate_str = str(row.get('RELATE', '')).strip()
        related_str = str(row.get('RELATED', '')).strip()

        is_family = False

        # Check RELATE code (1 to 9)
        if relate_str.isdigit() and 1 <= int(relate_str) <= 9:
            is_family = True
        # Check RELATED code (100 to 999) if RELATE is missing/different
        elif related_str.isdigit() and 100 <= int(related_str) <= 999:
            is_family = True
        # Check text labels just in case the CSV isn't fully numeric
        else:
            txt = (relate_str + " " + related_str).lower()
            if any(keyword in txt for keyword in ['head', 'spouse', 'wife', 'child', 'parent', 'sibling', 'grand']):
                is_family = True

        if not is_family:
            continue

        histid = str(row.get('HISTID', '')).strip()
        year = str(row.get('YEAR', '')).strip()
        serial = str(row.get('SERIAL', '')).strip()
        pernum = str(row.get('PERNUM', '')).strip()
        # Safely default to '1' if the CSV provides a completely blank string instead of None
        famunit = str(row.get('FAMUNIT') or '1').strip()

        poploc = str(row.get('POPLOC', '0')).strip()
        momloc = str(row.get('MOMLOC', '0')).strip()

        # DECISION: Use POPLOC and MOMLOC to assign the exact parent HISTID directly to the child.
        # This means the database natively understands the bloodline without needing future Python processing.
        father_histid = pernum_to_histid.get(poploc) if poploc != '0' else None
        mother_histid = pernum_to_histid.get(momloc) if momloc != '0' else None

        # DECISION: Build a unique family ID using Year, Serial (House), and FamUnit (Nuclear Family).
        family_id = f"{year}_{serial}_{famunit}"

        # DECISION: Capture the Head of Household and Spouse directly into the family record as we iterate.
        if family_id not in families_dict:
            families_dict[family_id] = {
                'year': year, 'serial': serial, 'famunit': famunit,
                'head_histid': None, 'spouse_histid': None,
                'hhtype': str(row.get('HHTYPE', '')).strip(),
                'numprec': str(row.get('NUMPREC', '')).strip(),
                'pernum': pernum,
                'eldch': str(row.get('ELDCH', '')).strip(),
                'yngch': str(row.get('YNGCH', '')).strip(),
                'relate': str(row.get('RELATE', '')).strip()
            }
            individuals_by_fam[family_id] = []

        # DECISION: Catch Head and Spouse. IPUMS codes can be 1-digit (RELATE) or 4-digit (RELATED like 0101).
        related_pad = str(row.get('RELATED', '')).zfill(4).lower()
        relate_str = str(row.get('RELATE', '')).strip()
        txt = (relate_str + " " + related_pad).lower()

        if relate_str in ('1', '01') or related_pad.startswith('01') or 'head' in txt:
            families_dict[family_id]['head_histid'] = histid
        elif relate_str in ('2', '02') or related_pad.startswith('02') or 'spouse' in txt or 'wife' in txt:
            families_dict[family_id]['spouse_histid'] = histid

        # DECISION: Never allow NULL or blank names. If the IPUMS 100% database lacks names,
        # we assign a highly unique placeholder ("Future Bosselstink"). Downstream GEDCOM overlays
        # will explicitly look for and overwrite these placeholders with true historical names.
        first_name = str(row.get('NAMEFRST', '')).strip()
        last_name = str(row.get('NAMELAST', '')).strip()

        if not first_name:
            first_name = "Future"
        if not last_name:
            last_name = "Bosselstink"

        # DECISION: The JSON Bread Crumbs. Serialize the entire raw CSV row into a JSON string.
        raw_data_json = json.dumps(row)

        individuals_by_fam[family_id].append((
            histid, first_name, last_name, year, row.get('SAMPLE'), serial, pernum, famunit,
            row.get('AGE'), row.get('SEX'), row.get('BIRTHYR'), 
            row.get('BIRTHMO'), row.get('MARRNOYRS'),
            row.get('BPLD') or row.get('BPL'), row.get('FBPLD') or row.get('FBPL'), 
            row.get('MBPLD') or row.get('MBPL'),
            father_histid, mother_histid, family_id, raw_data_json
        ))

    final_inds = []
    final_fams = []

    # DECISION: Lone Wolf Filter. "Don't make a family for one person."
    # We only create a 'families' record if the unit has more than 1 member.
    # However, we will now KEEP the individual record for lone wolves, but set their family_id to NULL.
    for fid, data in families_dict.items():
        family_members = individuals_by_fam[fid]

        if len(family_members) > 1:
            # This is a valid family, process as before.
            final_fams.append(
                (fid, data['year'], data['serial'], data['famunit'], data['head_histid'], data['spouse_histid'],
                 data['hhtype'], data['numprec'], data['pernum'], data['eldch'], data['yngch'], data['relate']))
            final_inds.extend(family_members)
        elif len(family_members) == 1:
            # This is a lone wolf. Keep the individual, but sever the family link.
            lone_wolf_tuple = family_members[0]
            list_version = list(lone_wolf_tuple)
            list_version[16] = None  # Set family_id (the 17th element) to None
            final_inds.append(tuple(list_version))

    return final_inds, final_fams


# ==============================================================================
# INGESTION LOOP
# ==============================================================================
def ingest_to_vault(input_csv, logger, record_limit=None):
    logger.info(f"Opening CSV file for sequential read: {input_csv}")

    conns_by_year = {}
    ind_batch_by_year = {}
    fam_batch_by_year = {}

    def get_db(year):
        if year not in conns_by_year:
            db_path = os.path.join(VAULT_DIR, f"YearVault_{year}.db")
            if not os.path.exists(db_path):
                setup_database(db_path, logger)

            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys = ON;")
            conns_by_year[year] = conn
            ind_batch_by_year[year] = []
            fam_batch_by_year[year] = []
        return conns_by_year[year]

    ind_insert_query = """
                       INSERT \
                       OR IGNORE INTO individuals 
        (histid, first_name, last_name, year, sample, serial, pernum, famunit, 
         age, sex, birthyr, birthmo, marrnoyrs, bpld, fbpl, mbpl, father_histid, mother_histid, family_id, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                       """

    fam_insert_query = """
                       INSERT \
                       OR IGNORE INTO families 
        (family_id, year, serial, famunit, head_histid, spouse_histid, hhtype, numprec, pernum, eldch, yngch, relate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                       """

    count = 0
    households_processed = 0
    start_time = time.time()

    with open(input_csv, mode='r', encoding='utf-8', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')
        current_serial = None
        household_buffer = []

        for row in reader:
            raw_serial = str(row.get('SERIAL', '')).strip()

            # Initialize on the very first row
            if current_serial is None:
                current_serial = raw_serial

            # DECISION: Sequential Household Buffering. The CSV is historically ordered by the census taker.
            # Everyone in the same house (SERIAL) is listed sequentially. We buffer rows in memory until
            # the SERIAL changes, meaning we have the complete house and can process them as a single atomic unit.
            if raw_serial != current_serial:
                inds, fams = process_household(household_buffer)

                hh_year = None
                if fams:
                    hh_year = fams[0][1]
                elif inds:
                    hh_year = inds[0][3]

                if hh_year:
                    get_db(hh_year)
                    ind_batch_by_year[hh_year].extend(inds)
                    fam_batch_by_year[hh_year].extend(fams)

                    if len(fam_batch_by_year[hh_year]) >= BATCH_SIZE:
                        conn = conns_by_year[hh_year]
                        cursor = conn.cursor()
                        cursor.executemany(fam_insert_query, fam_batch_by_year[hh_year])
                        cursor.executemany(ind_insert_query, ind_batch_by_year[hh_year])
                        conn.commit()
                        ind_batch_by_year[hh_year] = []
                        fam_batch_by_year[hh_year] = []

                households_processed += 1
                count += len(household_buffer)

                if households_processed % 100_000 == 0:
                    logger.info(f"  -> Processed {households_processed:,} households ({count:,} individuals)...")

                # Reset the buffer for the new household
                household_buffer = [row]
                current_serial = raw_serial

                # DECISION: Graceful Shutdown. By checking the limit here and clearing the buffer,
                # we ensure we don't commit a partially-read family if the limit is reached mid-household.
                if record_limit and count >= record_limit:
                    logger.info(f"  -> Reached record limit ({record_limit:,}). Stopping early for review.")
                    household_buffer = []  # Clear the buffer so we don't insert a partial household
                    break
            else:
                # Still in the same household, add to buffer
                household_buffer.append(row)

        # Catch the final household buffer when the file ends
        if household_buffer:
            inds, fams = process_household(household_buffer)

            hh_year = None
            if fams:
                hh_year = fams[0][1]
            elif inds:
                hh_year = inds[0][3]

            if hh_year:
                get_db(hh_year)
                fam_batch_by_year[hh_year].extend(fams)
                ind_batch_by_year[hh_year].extend(inds)

            count += len(household_buffer)
            households_processed += 1

        for year, conn in conns_by_year.items():
            try:
                if fam_batch_by_year[year]:
                    cursor = conn.cursor()
                    cursor.executemany(fam_insert_query, fam_batch_by_year[year])
                    cursor.executemany(ind_insert_query, ind_batch_by_year[year])
                    conn.commit()
            finally:
                conn.close()

    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"  [{os.path.basename(input_csv)}]  DONE — {count:,} records in {elapsed} min.")


# ==============================================================================
# INDEX OPTIMIZATION
# ==============================================================================
def build_indices(vault_dir, logger):
    """
    Builds database indices AFTER the bulk ingestion is complete.
    Creating indices before inserting 816 million rows dramatically slows down ingestion.
    """
    logger.info("Building indices for downstream queries... (This may take a while)")
    for filename in os.listdir(vault_dir):
        if filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename:
            db_path = os.path.join(vault_dir, filename)
            logger.info(f"  -> Indexing {filename}...")
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_individuals_parents ON individuals(father_histid, mother_histid);")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_individuals_names ON individuals(last_name, first_name);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_year_serial ON families(year, serial);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_family ON individuals(family_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_head ON families(head_histid);")
    logger.info("Indices built successfully!")


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Ingest census CSVs into a relational SQLite vault.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop reading after this many individuals (0 for all).")
    args = parser.parse_args()

    record_limit = args.limit if args.limit > 0 else None

    main_logger = gen_logging.setup_logging(logger_name="MAIN")

    main_logger.info("====================================================")
    main_logger.info("  RELATIONAL DATABASE INGESTION (SINGLE THREADED)")
    main_logger.info("====================================================")

    if os.path.exists(VAULT_DIR):
        main_logger.info(f"Starting fresh! Clearing old databases in {VAULT_DIR}...")
        for filename in os.listdir(VAULT_DIR):
            if filename.startswith("YearVault_") and filename.endswith(".db"):
                try:
                    os.remove(os.path.join(VAULT_DIR, filename))
                except OSError:
                    pass
    else:
        os.makedirs(VAULT_DIR, exist_ok=True)

    csv_files = [f for f in os.listdir(input_directory) if f.endswith(".csv")]

    for filename in csv_files:
        file_path = os.path.join(input_directory, filename)
        ingest_to_vault(file_path, main_logger, record_limit)

    # Build indices at the very end of the script to guarantee max insert speed
    build_indices(VAULT_DIR, main_logger)

    main_logger.info("\nAll CSV files have been processed and loaded into the Relational Vault.")
