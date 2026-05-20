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
import logging
import os
import sqlite3
import time
from concurrent.futures import as_completed, ThreadPoolExecutor

import gen_logging
from genealogy_classes import Person
from project_globals import CODEBOOK

# ==============================================================================
# TUNING KNOBS
# ==============================================================================
MAX_WORKERS = 4
BATCH_SIZE = 100_000
MULTIPLE_DATABASE_FILES = True
db_name1 = r"d:\Data\Genealogy_Data\MasterVault_"
input_directory = r"D:\Data\Genealogy_Data\CSV"
CENSUS_FILE_PREFIX = "census-"
CREATE_PERSON_OBJECTS = True
WRITE_DEBUG_CSV = True
DEBUG_CSV_LIMIT = 5000
DEBUG_OUTPUT_DIR = r"E:\Users\Andy\PycharmProjects\Genealogy\debug"

# ==============================================================================
# COLUMNS
# ==============================================================================
TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NUMPREC", "SEX", "AGE", "BIRTHYR", "HHTYPE", "STATEICP", "COUNTYICP",
    "METAREAD", "CITY", "FARM", "NMOTHERS", "NFATHERS", "FAMUNIT", "FAMSIZE",
    "MOMLOC", "POPLOC", "SPLOC", "MOMRULE_HIST", "POPRULE_HIST", "SPRULE_HIST", "NCHILD", "NSIBS",
    "ELDCH", "YNGCH", "RELATED", "RACED", "BPLD", "NAMELAST", "NAMEFRST", "HISTID",
    "REEL", "PAGENO", "LINE", "MICROSEQ"
]


# ==============================================================================
# DATABASE SETUP
# ==============================================================================
def setup_database(db_path):
    logging.info(f"Database set up: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    columns_sql = "composite_id TEXT PRIMARY KEY, " + ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])
    cursor.execute(f"CREATE TABLE IF NOT EXISTS population ({columns_sql})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")
    conn.commit()
    conn.close()
    logging.info(f"Database ready: {db_path}")


# ==============================================================================
# INGEST FUNCTION
# ==============================================================================
def ingest_to_vault(input_csv, db_path):
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
        logging.info(f"  [{os.path.basename(input_csv)}] Debug CSV enabled. Writing to: {debug_csv_path}")
        debug_file = open(debug_csv_path, mode='w', encoding='utf-8', newline='')

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

            if WRITE_DEBUG_CSV and debug_writer and count <= DEBUG_CSV_LIMIT:
                decoded_row = row.copy()
                for key, value in row.items():
                    if value is None:
                        continue

                    # Strip hidden spaces from the CSV so it matches the JSON codebook correctly
                    clean_val = str(value).strip()
                    # Inline replace the numeric code with the translated text
                    text_val = CODEBOOK.get_code_value(key, clean_val)
                    if text_val is not None and str(text_val) != clean_val:
                        decoded_row[key] = text_val
                debug_writer.writerow(decoded_row)

            if CREATE_PERSON_OBJECTS and count <= 5:
                p = Person(codebook=CODEBOOK, **row)
                logging.info(f"\n{p}")

            year = row.get('YEAR', 'UNKN').strip()
            composite_id = f"{row.get('SAMPLE', '').strip()}_{row.get('SERIAL', '').strip()}_{row.get('PERNUM', '').strip()}_{count}"

            row_data = [composite_id]
            for col in TARGET_COLUMNS:
                row_data.append(row.get(col, None))

            batch.append(tuple(row_data))

            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                logging.info(f"  [{os.path.basename(input_csv)}]  {count:,} records")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    if debug_file:
        debug_file.close()

    conn.close()
    elapsed = round((time.time() - start_time) / 60, 2)
    logging.info(f"  [{os.path.basename(input_csv)}]  DONE — {count:,} records in {elapsed} min.")
    return count, elapsed


# ==============================================================================
# THREAD WORKER
# ==============================================================================
def process_file(filename, input_directory):
    file_path = os.path.join(input_directory, filename)

    year = 'ALL'
    if MULTIPLE_DATABASE_FILES:
        try:
            year = filename.split('-')[1].split('.')[0]
        except IndexError:
            year = 'unknown'
        db_name = db_name1 + year + ".db"
        setup_database(db_name)
    else:
        db_name = db_name1 + "ALL.db"

    logging.info(f"\n--- [{filename}]  Thread starting → {db_name} ---")

    wall_start = time.time()
    record_count, elapsed_min = ingest_to_vault(file_path, db_name)
    wall_end = time.time()

    dtime = (wall_end - wall_start) * 1000
    rec_per_sec = record_count / dtime if dtime > 0 else 0
    logging.info(f"   record_count        : {record_count}")
    logging.info(f"   dtime milliseconds  : {dtime}")
    logging.info(f"   Rec per MS          : {rec_per_sec}\n")

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
    gen_logging.setup_logging()

    logging.info("====================================================")
    logging.info(f"  MAX_WORKERS              : {MAX_WORKERS}")
    logging.info(f"  BATCH_SIZE               : {BATCH_SIZE}")
    logging.info(f"  MULTIPLE_DATABASE_FILES  : {MULTIPLE_DATABASE_FILES}")
    logging.info("====================================================")

    if not MULTIPLE_DATABASE_FILES:
        db_name = db_name1 + r"ALL.db"
        setup_database(db_name)

    csv_files = [f for f in os.listdir(input_directory) if (f.startswith(CENSUS_FILE_PREFIX) and f.endswith(".csv"))]
    if args.files is not None:
        csv_files = csv_files[:args.files]

    logging.info(f"\nFound {len(csv_files)} CSV file(s). Launching up to {MAX_WORKERS} file processing thread(s).\n")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="CensusWorker") as executor:
        future_to_file = {executor.submit(process_file, fname, input_directory): fname for fname in csv_files}
        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as ex:
                logging.error(f"\n!!! ERROR processing {fname}: {ex}", exc_info=True)

    logging.info("\n" + "=" * 60)
    logging.info(f"  THREAD SUMMARY   (MAX_WORKERS={MAX_WORKERS}, BATCH_SIZE={BATCH_SIZE:,})")
    logging.info("=" * 60)
    logging.info(f"  {'Year':<8}  {'Records':>12}  {'Minutes':>8}  {'File'}")
    logging.info(f"  {'-' * 8}  {'-' * 12}  {'-' * 8}  {'-' * 15}")

    for r in sorted(results, key=lambda x: x["year"]):
        logging.info(f"  {r['year']:<8}  {r['records']:>12,}  {r['elapsed_min']:>8.2f}  {r['filename']}")

    total_records = sum(r["records"] for r in results)
    logging.info(f"\n  Total records across all files : {total_records:,}")
    logging.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    logging.info("")
