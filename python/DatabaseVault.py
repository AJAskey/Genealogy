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
--------------------------------
"""

import argparse
import csv
import datetime
import json
import os
import sqlite3
import time
import sys

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
BATCH_SIZE = 5_000  # Number of *Households* to buffer before committing to DB
MASTER_DB = r"D:\Data\Genealogy_Data\MasterVault_Relational.db"
input_directory = r"C:\tempc\ShortTermCSVfiles"

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
    
    # DECISION: Enforce Relational Integrity. SQLite defaults to OFF. Turning this ON ensures
    # we cannot insert an individual into a family_id that doesn't exist, preventing orphaned records.
    cursor.execute("PRAGMA foreign_keys = ON;")

    # For clean testing, drop the tables so every run is fresh
    cursor.execute("DROP TABLE IF EXISTS individuals;")
    cursor.execute("DROP TABLE IF EXISTS families;")

    # DECISION: The Families Table represents the "Nuclear Family Unit", NOT just the physical house.
    # By tracking 'famunit', we separate multiple families living under the same roof (e.g., boarders, servants).
    # We also extract core metrics (head_histid, spouse_histid, numprec) up to the family level 
    # to make downstream querying incredibly fast without needing complex JOINs.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS families (
            family_id TEXT PRIMARY KEY,
            year INTEGER,
            serial TEXT,
            famunit TEXT,
            head_histid TEXT,
            spouse_histid TEXT,
            hhtype TEXT,
            numprec TEXT,
            pernum TEXT,
            eldch TEXT,
            yngch TEXT,
            relate TEXT
        )
    ''')

    # DECISION: The Individuals Table stores the raw demographics and links to the Family Table via Foreign Key.
    # The 'raw_data' column acts as our "Bread Crumbs", storing the entire JSON row so we 
    # never lose any of the 50+ IPUMS variables, even if we don't explicitly parse them into columns today.
    # HISTID is used as the Primary Key because IPUMS guarantees it is a universally unique, permanent ID.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS individuals (
            histid TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            year INTEGER,
            sample TEXT,
            serial TEXT,
            pernum TEXT,
            famunit TEXT,
            age INTEGER,
            sex TEXT,
            birthyr INTEGER,
            bpld TEXT,
            fbpl TEXT,
            mbpl TEXT,
            father_histid TEXT,
            mother_histid TEXT,
            family_id TEXT,
            raw_data TEXT,  -- The Bread Crumbs! (JSON)
            FOREIGN KEY (family_id) REFERENCES families(family_id)
        )
    ''')
    
    conn.commit()
    logger.info(f"Disconnecting from database (Setup): {db_path}")
    conn.close()
    logger.info(f"Database ready: {db_path}")

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
            row.get('AGE'), row.get('SEX'), row.get('BIRTHYR'), row.get('BPLD'), 
            row.get('FBPL'), row.get('MBPL'),
            father_histid, mother_histid, family_id,
            raw_data_json
        ))
        
    final_inds = []
    final_fams = []
    
    # DECISION: Lone Wolf Filter. "Don't make a family for one person."
    # We only insert families (and their individuals) if the family has more than 1 member.
    for fid, data in families_dict.items():
        if len(individuals_by_fam[fid]) > 1:
            final_fams.append((fid, data['year'], data['serial'], data['famunit'], data['head_histid'], data['spouse_histid'],
                               data['hhtype'], data['numprec'], data['pernum'], data['eldch'], data['yngch'], data['relate']))
            final_inds.extend(individuals_by_fam[fid])
    
    return final_inds, final_fams

# ==============================================================================
# INGESTION LOOP
# ==============================================================================
def ingest_to_vault(input_csv, db_path, logger, record_limit=None):
    logger.info(f"Opening database for ingestion: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    ind_insert_query = """
        INSERT OR IGNORE INTO individuals 
        (histid, first_name, last_name, year, sample, serial, pernum, famunit, 
         age, sex, birthyr, bpld, fbpl, mbpl, father_histid, mother_histid, family_id, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    fam_insert_query = """
        INSERT OR IGNORE INTO families 
        (family_id, year, serial, famunit, head_histid, spouse_histid, hhtype, numprec, pernum, eldch, yngch, relate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    ind_batch = []
    fam_batch = []
    count = 0
    households_processed = 0
    start_time = time.time()

    logger.info(f"Opening CSV file for sequential read: {input_csv}")
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
                ind_batch.extend(inds)
                fam_batch.extend(fams)
                
                households_processed += 1
                count += len(household_buffer)
                
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

            # DECISION: Batch commits prevent the script from blowing up RAM on massive 100GB files.
            if len(fam_batch) >= BATCH_SIZE:
                # DECISION: Foreign Key constraints require that parent records (families) are inserted
                # before child records (individuals) pointing to them.
                cursor.executemany(fam_insert_query, fam_batch)
                cursor.executemany(ind_insert_query, ind_batch)
                conn.commit()
                
                logger.info(f"  -> Processed {households_processed:,} households ({count:,} individuals)...")
                ind_batch = []
                fam_batch = []

        # Catch the final household buffer when the file ends
        if household_buffer:
            inds, fams = process_household(household_buffer)
            fam_batch.extend(fams)
            ind_batch.extend(inds)
            count += len(household_buffer)
            households_processed += 1

        if fam_batch:
            cursor.executemany(fam_insert_query, fam_batch)
            cursor.executemany(ind_insert_query, ind_batch)
            conn.commit()

    conn.close()
    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"  [{os.path.basename(input_csv)}]  DONE — {count:,} records in {elapsed} min.")


# ==============================================================================
# INDEX OPTIMIZATION
# ==============================================================================
def build_indices(db_path, logger):
    """
    Builds database indices AFTER the bulk ingestion is complete. 
    Creating indices before inserting 816 million rows dramatically slows down ingestion.
    """
    logger.info("Building indices for downstream queries... (This may take a while on the full 100% database)")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_parents ON individuals(father_histid, mother_histid);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_names ON individuals(last_name, first_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_year_serial ON families(year, serial);")
        logger.info("Indices built successfully!")

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Ingest census CSVs into a relational SQLite vault.")
    parser.add_argument("--limit", type=int, default=100_000, help="Stop reading after this many individuals (0 for all).")
    args = parser.parse_args()
    
    record_limit = args.limit if args.limit > 0 else None

    main_logger = gen_logging.setup_logging(logger_name="MAIN")

    main_logger.info("====================================================")
    main_logger.info("  RELATIONAL DATABASE INGESTION (SINGLE THREADED)")
    main_logger.info("====================================================")

    setup_database(MASTER_DB, main_logger)

    csv_files = [f for f in os.listdir(input_directory) if f.endswith(".csv")]

    for filename in csv_files:
        file_path = os.path.join(input_directory, filename)
        ingest_to_vault(file_path, MASTER_DB, main_logger, record_limit)
        
    # Build indices at the very end of the script to guarantee max insert speed
    build_indices(MASTER_DB, main_logger)
        
    main_logger.info("\nAll CSV files have been processed and loaded into the Relational Vault.")
