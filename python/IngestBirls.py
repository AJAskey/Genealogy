r"""
-----------------------------------
File: IngestBirls.py

Summary: Ingests the VA BIRLS Death File (and SSDI) CSV chunks into a new, 
         isolated SQLite database (DeathIndexVault.db).

Design:
  - Uses ProcessPoolExecutor to ingest multiple chunk files in parallel.
  - Target DB: D:\Data\Genealogy_Data\DeathIndexVault.db
  - Table: birls_records
  - Uses WAL mode for thread-safe concurrent writes.
  - Auto-detects Tab vs Comma delimiters.

Inputs:  Directory containing the BIRLS CSV chunks.
Outputs: D:\Data\Genealogy_Data\DeathIndexVault.db
-----------------------------------
"""
import csv
import datetime
import os
import sqlite3
import time
from concurrent.futures import as_completed, ProcessPoolExecutor

import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MAX_WORKERS = 4
BATCH_SIZE = 100_000
DB_PATH = r"D:\Data\Genealogy_Data\DeathIndexVault.db"
# Point directly to the main folder containing the unsplit massive file
INPUT_DIRECTORY = r"E:\Users\Andy\PycharmProjects\Genealogy\data\BIRLS_database"

# Columns exactly as they appear in the BIRLS header
TARGET_COLUMNS = [
    "fn", "first", "middle", "last", "suffix", "ssn", "dob", "dod", "gender",
    "branch_1", "entered_1", "seperated_1",
    "branch_2", "entered_2", "seperated_2",
    "branch_3", "entered_3", "seperated_3"
]


def setup_database(logger):
    """Creates the DeathIndexVault database and the BIRLS table."""
    logger.info(f"Setting up Auxiliary DB: {DB_PATH}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")

    columns_sql = ", ".join([f"{col} TEXT" for col in TARGET_COLUMNS])

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS birls_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            {columns_sql}
        )
    """)

    # Create indexes on names and dates for lightning-fast lookups during the Analyst matching phase
    logger.info("Building indexes on first, last, dob, and ssn...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_birls_last ON birls_records (last)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_birls_first ON birls_records (first)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_birls_dob ON birls_records (dob)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_birls_ssn ON birls_records (ssn)")

    conn.commit()
    conn.close()


def ingest_birls_file(input_csv, logger):
    """Reads a BIRLS CSV/TSV file and bulk-inserts it into the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cols_string = ", ".join(TARGET_COLUMNS)
    placeholders = ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT INTO birls_records ({cols_string}) VALUES ({placeholders})"

    batch = []
    count = 0
    skipped = 0
    start_time = time.time()

    with open(input_csv, mode='r', encoding='utf-8', errors='replace') as infile:
        # Auto-detect if the file is Tab-separated or Comma-separated
        first_line = infile.readline()
        delimiter = '\t' if '\t' in first_line else ','
        infile.seek(0)

        logger.info(f"Opening file: {os.path.basename(input_csv)} (Delimiter: '{delimiter}')")
        reader = csv.DictReader(infile, delimiter=delimiter)

        # Force all CSV headers to lowercase and remove hidden BOM characters
        if reader.fieldnames:
            reader.fieldnames = [str(col).strip().lower().replace('\ufeff', '') for col in reader.fieldnames]

        for row in reader:
            # Check for actual data to prevent blank/garbage records from entering the vault
            first_name = str(row.get('first', '')).strip()
            last_name = str(row.get('last', '')).strip()
            ssn = str(row.get('ssn', '')).strip()
            dob = str(row.get('dob', '')).strip()

            # A record is useless to our matching engine if it lacks a name
            if not first_name and not last_name:
                skipped += 1
                continue

            count += 1
            row_data = tuple(str(row.get(col, '')).strip() for col in TARGET_COLUMNS)
            batch.append(row_data)

            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                logger.info(f"  [{os.path.basename(input_csv)}]  {count:,} records inserted...")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    conn.close()
    elapsed = round((time.time() - start_time) / 60, 2)
    logger.info(f"  [{os.path.basename(input_csv)}]  DONE — {count:,} inserted | {skipped:,} blanks skipped | {elapsed} min.")
    return count, elapsed


def process_file(filename, input_dir):
    """Worker function for ProcessPoolExecutor."""
    file_path = os.path.join(input_dir, filename)
    logger = gen_logging.setup_logging(logger_name=f"BIRLS_{filename.split('.')[0]}")

    logger.info(f"\n--- [{filename}] Thread starting ---")
    wall_start = time.time()
    record_count, elapsed_min = ingest_birls_file(file_path, logger)
    wall_end = time.time()

    dtime = (wall_end - wall_start) * 1000
    rec_per_ms = record_count / dtime if dtime > 0 else 0

    logger.info(f"  [{filename}] record_count       : {record_count:,}")
    logger.info(f"  [{filename}] dtime milliseconds : {dtime:,.2f}")
    logger.info(f"  [{filename}] Rec per MS         : {rec_per_ms:,.2f}\n")

    return {"filename": filename, "records": record_count, "elapsed_min": elapsed_min}


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging(logger_name="MAIN_BIRLS")
    main_logger.info("====================================================")
    main_logger.info("  BIRLS / DEATH INDEX INGESTION STARTING")
    main_logger.info(f"  MAX_WORKERS : {MAX_WORKERS}")
    main_logger.info("====================================================")

    setup_database(main_logger)

    if not os.path.exists(INPUT_DIRECTORY):
        main_logger.error(f"Input directory not found: {INPUT_DIRECTORY}")
        exit(1)

    # Process both standard CSVs and TXTs
    data_files = [f for f in os.listdir(INPUT_DIRECTORY) if f.endswith('.csv') or f.endswith('.txt')]

    if not data_files:
        main_logger.error(f"No CSV or TXT files found in {INPUT_DIRECTORY}")
        exit(1)

    main_logger.info(f"Found {len(data_files)} file(s). Launching up to {MAX_WORKERS} workers.\n")

    results = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_file, fname, INPUT_DIRECTORY): fname for fname in data_files}
        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                res = future.result()
                results.append(res)
            except Exception as ex:
                main_logger.error(f"!!! ERROR processing {fname}: {ex}", exc_info=True)

    main_logger.info("\n" + "=" * 60)
    main_logger.info(f"  THREAD SUMMARY (BIRLS INGESTION)")
    main_logger.info("=" * 60)

    total_records = 0
    for r in results:
        main_logger.info(f"  {r['records']:>12,} records | {r['elapsed_min']:>6.2f} min | {r['filename']}")
        total_records += r['records']

    main_logger.info(f"\n  Total records successfully ingested: {total_records:,}")
    main_logger.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
