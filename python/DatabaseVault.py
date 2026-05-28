"""
-----------------------------------
File: DatabaseVault.py

Summary: Creates a Database for each year of census data, using a
         thread pool so multiple CSV files are ingested in parallel.

Design:  One thread per CSV file, up to MAX_WORKERS at a time.
         Each thread gets its own SQLite connection (no shared state,
         no locking needed between threads).

Inputs:  A directory of CSV files from IPUMS, one file per census year.

Outputs: One SQLite database file per year.
--------------------------------
"""

import argparse
import csv
import datetime
import os
import re
import sqlite3
import time
from concurrent.futures import as_completed, ProcessPoolExecutor

import gen_logging
from genealogy_classes import Person
from project_globals import CODEBOOK

# ==============================================================================
# TUNING KNOBS
# ==============================================================================
MAX_WORKERS = 4
BATCH_SIZE = 100_000
MULTIPLE_DATABASE_FILES = False
SINGLE_DB_SUFFIX = "ALL"  # Change to "ALLs" when running the samples CSV!
db_name1 = r"d:\Data\Genealogy_Data\MasterVault_"
input_directory = r"C:\tempc\ShortTermCSVfiles"
CREATE_PERSON_OBJECTS = True
WRITE_DEBUG_CSV = True
DEBUG_CSV_LIMIT = 5000
DEBUG_OUTPUT_DIR = r"E:\Users\Andy\PycharmProjects\Genealogy\debug"

# ==============================================================================
# COLUMNS
# ==============================================================================
TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NUMPREC", "SEX", "AGE", "BIRTHYR", "BPLD", "NAMELAST", "NAMEFRST", "HHTYPE",
    "STATEICP", "COUNTYICP", "METAREAD", "CITY", "FARM", "FAMUNIT", "FAMSIZE", "NMOTHERS", "NFATHERS", "NCHILD",
    "NSIBS", "MOMLOC", "POPLOC", "SPLOC", "MOMRULE_HIST", "POPRULE_HIST", "SPRULE_HIST",
    "ELDCH", "YNGCH", "RELATED", "RACED", "HISTID",
    "REEL", "PAGENO", "LINE", "MICROSEQ"
]


# ==============================================================================
# DATABASE SETUP
# ==============================================================================
def setup_database(db_path, logger):
    logger.info(f"Connecting to database (Setup): {db_path}")
    logger.info(f"Database set up: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    columns_sql = "composite_id TEXT PRIMARY KEY, " + ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])
    cursor.execute(f"CREATE TABLE IF NOT EXISTS population ({columns_sql})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")
    conn.commit()
    logger.info(f"Disconnecting from database (Setup): {db_path}")
    conn.close()
    logger.info(f"Database ready: {db_path}")


# ==============================================================================
# INGEST FUNCTION
# ==============================================================================
def ingest_to_vault(input_csv, db_path, logger):
    logger.info(f"Connecting to database (Ingest): {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cols_string = "composite_id, " + ", ".join([col.lower() for col in TARGET_COLUMNS])
    placeholders = "?, " + ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT OR IGNORE INTO population ({cols_string}) VALUES ({placeholders})"

    batch = []
    count = 0
    start_time = time.time()

    debug_file = None
    if WRITE_DEBUG_CSV:
        os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
        debug_csv_path = os.path.join(DEBUG_OUTPUT_DIR, f"debug_{os.path.basename(input_csv)}")
        logger.info(f"  [{os.path.basename(input_csv)}] Debug CSV enabled. Writing to: {debug_csv_path}")
        debug_file = open(debug_csv_path, mode='w', encoding='utf-8', newline='')

    logger.info(f"Opening CSV file for reading: {input_csv}")
    with open(input_csv, mode='r', encoding='utf-8', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        debug_writer = None
        if WRITE_DEBUG_CSV and debug_file:
            # Write the exact original headers
            debug_writer = csv.DictWriter(debug_file, fieldnames=reader.fieldnames)
            debug_writer.writeheader()

        available_cols = set(reader.fieldnames) if reader.fieldnames else set()

        for row in reader:
            count += 1

            # Extract raw values to build the St. Joe's ID BEFORE they get translated by the Codebook
            raw_sample = str(row.get('SAMPLE', '')).strip()
            raw_serial = str(row.get('SERIAL', '')).strip()
            raw_pernum = str(row.get('PERNUM', '')).strip()

            # Create the permanent, repeatable St. Joe's ID 
            composite_id = f"{raw_sample}_{raw_serial}_{raw_pernum}"

            # Fields that are pure data/IDs and should NEVER be translated via Codebook
            DO_NOT_TRANSLATE = {
                "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NAMELAST", "NAMEFRST", 
                "HISTID", "REEL", "PAGENO", "LINE", "MICROSEQ", "AGE", "BIRTHYR"
            }

            # 1. Clean and translate the row globally BEFORE doing anything else
            for key, value in row.items():
                if value is None:
                    continue

                clean_val = str(value).strip()

                # Bypass the codebook for IDs, names, and source locators
                if key.upper() in DO_NOT_TRANSLATE:
                    row[key] = clean_val
                    continue

                # Attempt robust lookup handling zero-padding mismatches between CSV and JSON
                text_val = CODEBOOK.get_code_value(key.upper(), clean_val)

                # If direct lookup fails, try numeric padding combinations
                if text_val is None and clean_val.isdigit():
                    num_str = str(int(clean_val))  # Strip leading zeroes
                    text_val = CODEBOOK.get_code_value(key.upper(), num_str)
                    if text_val is None:
                        text_val = CODEBOOK.get_code_value(key.upper(), num_str.zfill(2))
                    if text_val is None:
                        text_val = CODEBOOK.get_code_value(key.upper(), num_str.zfill(3))
                    if text_val is None:
                        text_val = CODEBOOK.get_code_value(key.upper(), num_str.zfill(4))

                # Overwrite the row dictionary with the clean/translated value
                if text_val is not None and str(text_val) != clean_val:
                    row[key] = text_val
                else:
                    row[key] = clean_val

            # 2. Write to debug CSV if needed
            if WRITE_DEBUG_CSV and debug_writer and count <= DEBUG_CSV_LIMIT:
                debug_writer.writerow(row)

            if CREATE_PERSON_OBJECTS and count <= 5:
                p = Person(codebook=CODEBOOK, **row)
                logger.info(f"\n{p}")

            row_data = [composite_id]
            for col in TARGET_COLUMNS:
                row_data.append(row.get(col, None))

            batch.append(tuple(row_data))

            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                logger.info(f"  [{os.path.basename(input_csv)}]  {count:,} records")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    logger.info(f"Closing CSV file: {input_csv}")
    if debug_file:
        debug_file.close()

    logger.info(f"Disconnecting from database (Ingest): {db_path}")
    conn.close()
    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"  [{os.path.basename(input_csv)}]  DONE — {count:,} records in {elapsed} min.")
    return count, elapsed


# ==============================================================================
# THREAD WORKER
# ==============================================================================
def process_file(filename, input_directory):
    file_path = os.path.join(input_directory, filename)

    # Always extract the year so each thread gets its own distinct log file
    match = re.search(r'\d{4}', filename)
    year = match.group() if match else 'unknown'

    # Create a unique logger for this specific year/thread
    logger = gen_logging.setup_logging(logger_name=year)

    if MULTIPLE_DATABASE_FILES:
        db_name = db_name1 + year + ".db"
        setup_database(db_name, logger)
    else:
        db_name = db_name1 + f"{SINGLE_DB_SUFFIX}.db"

    logger.info(f"\n--- [{filename}]  Thread starting → {db_name} ---")

    wall_start = time.time()
    record_count, elapsed_min = ingest_to_vault(file_path, db_name, logger)
    wall_end = time.time()

    dtime = (wall_end - wall_start) * 1000
    rec_per_sec = record_count / dtime if dtime > 0 else 0
    logger.info(f"  [{filename}]  record_count        : {record_count:,}")
    logger.info(f"  [{filename}]  dtime milliseconds  : {dtime:,.2f}")
    logger.info(f"  [{filename}]  Rec per MS          : {rec_per_sec:,.2f}\n")

    return {
        "filename": filename,
        "year": year,
        "records": record_count,
        "elapsed_min": elapsed_min,
    }


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Ingest census CSVs into SQLite vaults.")
    parser.add_argument("--workers", "-w", type=int, default=MAX_WORKERS,
                        help=f"Number of parallel threads (default: {MAX_WORKERS})")
    parser.add_argument("--files", "-f", type=int, help="Max number of CSV files to process (default: all)")
    args = parser.parse_args()
    MAX_WORKERS = args.workers

    # Initial logging setup for the main process
    main_logger = gen_logging.setup_logging(logger_name="MAIN")

    main_logger.info("====================================================")
    main_logger.info(f"  MAX_WORKERS              : {MAX_WORKERS}")
    main_logger.info(f"  BATCH_SIZE               : {BATCH_SIZE}")
    main_logger.info(f"  MULTIPLE_DATABASE_FILES  : {MULTIPLE_DATABASE_FILES}")
    main_logger.info("====================================================")

    if not MULTIPLE_DATABASE_FILES:
        db_name = db_name1 + f"{SINGLE_DB_SUFFIX}.db"
        setup_database(db_name, main_logger)

    csv_files = [f for f in os.listdir(input_directory) if f.endswith(".csv")]
    if args.files is not None:
        csv_files = csv_files[:args.files]

    main_logger.info(
        f"\nFound {len(csv_files)} CSV file(s). Launching up to {MAX_WORKERS} file processing thread(s).\n")

    results = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_file, fname, input_directory): fname for fname in csv_files}
        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as ex:
                main_logger.error(f"\n!!! ERROR processing {fname}: {ex}", exc_info=True)

    main_logger.info("\n" + "=" * 60)
    main_logger.info(f"  THREAD SUMMARY   (MAX_WORKERS={MAX_WORKERS}, BATCH_SIZE={BATCH_SIZE:,})")
    main_logger.info("=" * 60)
    main_logger.info(f"  {'Year':<8}  {'Records':>12}  {'Minutes':>8}  {'File'}")
    main_logger.info(f"  {'-' * 8}  {'-' * 12}  {'-' * 8}  {'-' * 15}")

    for r in sorted(results, key=lambda x: x["year"]):
        main_logger.info(f"  {r['year']:<8}  {r['records']:>12,}  {r['elapsed_min']:>8.2f}  {r['filename']}")

    total_records = sum(r["records"] for r in results)
    main_logger.info(f"\n  Total records across all files : {total_records:,}")
    main_logger.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    main_logger.info("")
