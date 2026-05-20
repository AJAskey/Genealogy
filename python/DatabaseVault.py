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

Threading notes:
  - Python threads share memory but each thread opens its own
    sqlite3.connect(), so SQLite is never touched by two threads at once.
  - The GIL doesn't hurt us here because the bottleneck is disk I/O
    (reading CSV, writing SQLite), not pure CPU.  I/O releases the GIL,
    so threads genuinely run in parallel at the OS level.
  - If you later want pure CPU parallelism, swap ThreadPoolExecutor
    for ProcessPoolExecutor — the worker function signature is identical.

--------------------------------
"""

import argparse
import csv
import datetime
import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import as_completed, ThreadPoolExecutor

from genealogy_classes import Person
from project_globals import CODEBOOK  # Import the global codebook

import psutil

import gen_logging
import vault_stats

# ==============================================================================
# TUNING KNOBS
# ==============================================================================

# Maximum number of concurrent threads (1 means sequential execution)
MAX_WORKERS = 4
# Number of records to accumulate before executing a bulk database commit
BATCH_SIZE = 100_000

# Toggle whether to split outputs by year or merge them all into one database.
# Set to False to build one massive MasterVault_ALL.db (ideal for cross-census queries)
MULTIPLE_DATABASE_FILES = False

# Database configuration paths and defaults
db_name1 = r"d:\Data\Genealogy_Data\MasterVault_"
input_directory = r"D:\Data\Genealogy_Data\CSV"
yr = 'ALL'
CENSUS_FILE_PREFIX = "census-1860"

# Toggle to instantiate the Person object dynamically during ingest
CREATE_PERSON_OBJECTS = True

# Toggle to write a sample of the parsed CSV rows to a new file for visual inspection
WRITE_DEBUG_CSV = True
# Limit the debug CSV to a small number of rows so we don't duplicate 18 GB files!
DEBUG_CSV_LIMIT = 5000
DEBUG_OUTPUT_DIR = r"E:\Users\Andy\PycharmProjects\Genealogy\debug"
#
# ==============================================================================
# >>> SINGLE DATABASE PATH  ← change this to wherever you want the file <<<
# ==============================================================================


# ==============================================================================
# COLUMNS
# ==============================================================================

TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NUMPREC", "BIRTHYR", "AGE", "SEX", "HHTYPE", "STATEICP", "COUNTYICP",
    "METAREAD", "CITY", "FARM", "NMOTHERS", "NFATHERS", "FAMUNIT", "FAMSIZE", "MOMLOC",
    "MOMRULE_HIST", "POPLOC", "POPRULE_HIST", "SPLOC", "SPRULE_HIST", "NCHILD", "NSIBS", "ELDCH", "YNGCH",
    "RELATED", "RACED", "BPLD", "NAMELAST", "NAMEFRST", "HISTID"
]


# ==============================================================================
# DATABASE SETUP  — called ONCE at startup, not per thread
# ==============================================================================


def setup_database(db_path):
    """
    Creates the population table and index in the single master database.
    Safe to call multiple times — IF NOT EXISTS protects against duplicates.
    
    Args:
        db_path (str): The file path to the SQLite database to initialize.
    """
    logging.info(f"Database set up: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable WAL mode so multiple threads can write without stomping on each other
    cursor.execute("PRAGMA journal_mode=WAL")

    # Build the schema dynamically from the TARGET_COLUMNS list
    columns_sql = "composite_id TEXT PRIMARY KEY, "
    columns_sql += ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])

    # Create the main table and a sample index for performance
    cursor.execute(f"CREATE TABLE IF NOT EXISTS population ({columns_sql})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")

    conn.commit()
    conn.close()
    logging.info(f"Database ready: {db_path}")


# ==============================================================================
# INGEST FUNCTION  — each thread calls this for its own CSV file
# ==============================================================================

def ingest_to_vault(input_csv, db_path):
    """
    Reads one CSV file and writes it into the shared master database.
    Missing columns are filled with NULL — no crash, no ERR values.
    Each thread opens its own connection (WAL mode makes this safe).
    
    Args:
        input_csv (str): Path to the CSV file to be ingested.
        db_path (str): Path to the target SQLite database.
        
    Returns:
        tuple: (Total number of records processed, Elapsed time in minutes)
    """
    conn = sqlite3.connect(db_path)

    # WAL mode per connection too, just to be safe
    conn.execute("PRAGMA journal_mode=WAL")

    cursor = conn.cursor()

    # Prepare the bulk insert SQL statement dynamically
    cols_string = "composite_id, " + ", ".join([col.lower() for col in TARGET_COLUMNS])
    placeholders = "?, " + ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT OR IGNORE INTO population ({cols_string}) VALUES ({placeholders})"

    batch = []
    count = 0
    start_time = time.time()

    debug_file = None
    debug_writer = None

    # If the debug toggle is on, prepare a secondary CSV file for writing
    if WRITE_DEBUG_CSV:
        os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
        debug_csv_path = os.path.join(DEBUG_OUTPUT_DIR, f"debug_{os.path.basename(input_csv)}")
        logging.info(f"  [{os.path.basename(input_csv)}] Debug CSV enabled. Writing to: {debug_csv_path}")
        # Open the debug file for writing. Always use UTF-8!
        debug_file = open(debug_csv_path, mode='w', encoding='utf-8', newline='')

    # Enforcing UTF-8 encoding per project Golden Rules
    with open(input_csv, mode='r', encoding='utf-8', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        if WRITE_DEBUG_CSV and debug_file:
            # Initialize the writer with the exact same headers we just read
            debug_writer = csv.DictWriter(debug_file, fieldnames=reader.fieldnames)
            debug_writer.writeheader()

        # Figure out which TARGET_COLUMNS actually exist in THIS csv file.
        # Any column missing from the file will just get None (stored as NULL).
        available_cols = set(reader.fieldnames) if reader.fieldnames else set()

        for row in reader:
            count += 1

            # Write the row to our debug CSV file if we haven't hit the limit
            if WRITE_DEBUG_CSV and debug_writer and count <= DEBUG_CSV_LIMIT:
                debug_writer.writerow(row)

            # Only create the Person object if the toggle is turned on
            if CREATE_PERSON_OBJECTS:
                # Create Person p by unpacking the DictReader's dictionary directly
                # Pass the global CODEBOOK to enable rich, decoded logging
                p = Person(codebook=CODEBOOK, **row)
                # Log the decoded Person object for the first 5 records for debugging
                if count <= 5:
                    logging.info(f"\n{p}")

            # Extract identifiers to create a universally unique ID for the database
            serial = row.get('SERIAL', '').strip()
            pernum = row.get('PERNUM', '').strip()
            sample = row.get('SAMPLE', '').strip()

            # Include the year in the composite_id so records from different
            # census years never collide even if SERIAL/PERNUM repeat.
            year = row.get('YEAR', 'UNKN').strip()
            composite_id = f"{sample}_{serial}_{pernum}_{count}"

            row_data = [composite_id]
            # Map the CSV row data to our target schema, handling missing columns gracefully
            for col in TARGET_COLUMNS:
                if col in available_cols:
                    try:
                        row_data.append(row.get(col, None))
                        if row_data[-1] is not None:
                            row_data[-1] = row_data[-1].strip()
                    except Exception:
                        logging.warning(f"[{os.path.basename(input_csv)}] problem reading col: {col}")
                        row_data.append(None)
                else:
                    # Column doesn't exist in this CSV — store NULL quietly
                    row_data.append(None)

            batch.append(tuple(row_data))

            # Execute a batch commit when the batch limit is reached
            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                ts = datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')
                logging.info(f"  [{os.path.basename(input_csv)}]  {count:,} records")

        # Flush any remaining records that didn't fill the final batch
        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    # Clean up the debug file gracefully if we opened it
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
    """
    Called by the thread pool for each CSV file.
    Handles routing the CSV file to the correct database (either single or split by year).
    Records execution statistics for performance monitoring.
    
    Args:
        filename (str): Name of the CSV file.
        input_directory (str): The folder containing the CSV file.
        
    Returns:
        dict: Summary statistics about the processed file.
    """
    global db_name1, yr

    file_path = os.path.join(input_directory, filename)

    # Determine destination database logic
    if MULTIPLE_DATABASE_FILES:
        # Extract the year from standard census filenames (e.g., 'census-1850.csv')
        yr = filename.split('-')[1].split('.')[0] if '-' in filename else 'unknown'
        db_name = db_name1 + yr + ".db"
        setup_database(db_name)
    else:
        db_name = db_name1 + "ALL.db"

    logging.info(f"\n--- [{filename}]  Thread starting → {db_name} ---")

    # Snapshot hardware statistics prior to ingestion
    wall_start = time.time()
    cpu_before = psutil.Process().cpu_times()
    snap_before = vault_stats.get_system_snapshot()

    # Perform the actual data ingestion
    record_count, elapsed_min = ingest_to_vault(file_path, db_name)

    wall_end = time.time()
    cpu_after = psutil.Process().cpu_times()
    snap_after = vault_stats.get_system_snapshot()

    # Output performance differentials via custom stats module
    vault_stats.print_stats_report(
        label=f"File: {filename}",
        before=snap_before,
        after=snap_after,
        wall_seconds=wall_end - wall_start,
        cpu_times_before=cpu_before,
        cpu_times_after=cpu_after,
    )

    # Calculate throughput metrics
    dtime = (wall_end - wall_start) * 1000
    rec_per_sec = record_count / dtime if dtime > 0 else 0
    logging.info(f"   record_count        : {record_count}")
    logging.info(f"   dtime milliseconds  : {dtime}")
    logging.info(f"   Rec per MS          : {rec_per_sec}\n")

    return {
        "filename": filename,
        "year": yr,
        "records": record_count,
        "elapsed_min": elapsed_min,
        "wall_seconds": wall_end - wall_start,
    }


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == '__main__':
    # ---- Set up logging FIRST so every line below goes to file + console ----
    gen_logging.setup_logging()  # logs to console + file when run standalone

    # Set up command-line arguments to override tuning knobs dynamically
    parser = argparse.ArgumentParser(description="Ingest census CSVs into SQLite vaults.")
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=MAX_WORKERS,
        help=f"Number of parallel threads (default: {MAX_WORKERS})"
    )
    parser.add_argument(
        "--files", "-f",
        type=int,
        default=None,
        help="Max number of CSV files to process (default: all)"
    )
    args = parser.parse_args()
    MAX_WORKERS = args.workers

    vault_stats.print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_snap_before = vault_stats.get_system_snapshot()

    # set up creation of single db here before threads kick off
    if not MULTIPLE_DATABASE_FILES:
        db_name = db_name1 + r"ALL.db"
        setup_database(db_name)

    # Scan the input directory and gather all CSV files
    csv_files = [f for f in os.listdir(input_directory) if (f.startswith(CENSUS_FILE_PREFIX) and f.endswith(".csv"))]

    # --- NEW: cap the list if --files was specified ---
    if args.files is not None:
        csv_files = csv_files[:args.files]

    logging.info(f"input_directory  {input_directory} \n")
    logging.info(f"\nFound {len(csv_files)} CSV file(s).  Launching up to {MAX_WORKERS} file processing thread(s).\n")

    results = []

    # ThreadPoolExecutor works just like Java's ExecutorService.
    # submit() hands a job to the pool and returns a Future.
    # as_completed() yields each Future as it finishes (not in submission order).
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="CensusWorker") as executor:

        # Submit all jobs up front; the pool throttles to MAX_WORKERS at a time
        future_to_file = {
            executor.submit(process_file, fname, input_directory): fname
            for fname in csv_files
        }

        thread_id = 0
        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                thread_id += 1
                # Extract results from the completed thread.
                result = future.result()  # re-raises any exception from the thread
                results.append(result)
                logging.info(f"thread_id {thread_id} {threading.current_thread().name} complete")
            except Exception as ex:
                logging.error(f"\n!!! ERROR processing {fname}: {ex}")

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    logging.info("\n" + "=" * 60)
    logging.info(f"  THREAD SUMMARY   (MAX_WORKERS={MAX_WORKERS}, BATCH_SIZE={BATCH_SIZE:,})")
    logging.info("=" * 60)
    logging.info(f"  {'Year':<8}  {'Records':>12}  {'Minutes':>8} {'Rec_per_MS':>11}  {'File'}")
    logging.info(f"  {'-' * 8}  {'-' * 12}  {'-' * 8}  {'-' * 11}  {'-' * 15}")

    # Print per-file metrics, sorted chronologically by year
    for r in sorted(results, key=lambda x: x["year"]):
        ms = r["elapsed_min"] * 60_000.0
        rec_per_ms = r["records"] / ms if ms > 0 else 0.0
        logging.info(
            f"  {r['year']:<8}  {r['records']:>12,}  {r['elapsed_min']:>8.2f}  {rec_per_ms:>10.2f}  {r['filename']}")

    # Capture global runtime telemetry across the whole job session
    total_records = sum(r["records"] for r in results)
    session_wall_end = time.time()
    session_cpu_after = psutil.Process().cpu_times()
    session_snap_after = vault_stats.get_system_snapshot()

    vault_stats.print_stats_report(
        label="FULL SESSION TOTAL",
        before=session_snap_before,
        after=session_snap_after,
        wall_seconds=session_wall_end - session_wall_start,
        cpu_times_before=session_cpu_before,
        cpu_times_after=session_cpu_after,
    )

    total_wall_min = round((session_wall_end - session_wall_start) / 60, 2)
    ms = total_wall_min * 60_000.0
    rep_ms = total_records / ms if ms > 0 else 0.0
    logging.info(f"\n  Total records across all files : {total_records:,}")
    logging.info(f"  Records per millisecond        : {rep_ms}")
    logging.info(f"  Total wall-clock time          : {total_wall_min} minutes -> {ms} milliseconds")

logging.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
logging.info("")
