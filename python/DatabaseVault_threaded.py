"""
-----------------------------------
File: DatabaseVault_threaded.py

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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil

import vault_stats

# ==============================================================================
# TUNING KNOBS  ← play with these to find your sweet spot
# ==============================================================================

MAX_WORKERS = 4  # Number of threads running at the same time.
# Good starting values to benchmark:
#   2  → conservative, less disk contention
#   4  → sweet spot on most desktops with SSD
#   8  → worth trying on NVMe or RAID arrays
#   1  → single-threaded baseline for comparison
# Rule of thumb: more threads = more disk heads
# competing. If your files are on a spinning HDD,
# 2-3 is usually the ceiling before it gets worse.

BATCH_SIZE = 500_000  # Rows buffered in memory before each SQLite commit.
# Larger = fewer commits = faster, but uses more RAM.
# 500k is a solid default; try 250k if RAM is tight,
# or 1_000_000 if you have plenty of headroom.


# ==============================================================================
# COLUMNS  (unchanged from original)
# ==============================================================================

TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NUMPREC", "HHTYPE", "STATEICP", "COUNTYICP", "CITY", "FARM",
    "NMOTHERS", "NFATHERS", "FAMUNIT", "FAMSIZE", "MOMLOC", "POPLOC", "SPLOC", "NCHILD",
    "NSIBS", "ELDCH", "YNGCH", "RELATED", "SEX", "AGE", "BIRTHYR", "RACED", "BPLD",
    "NAMELAST", "NAMEFRST", "HISTID",
]


# ==============================================================================
# DATABASE FUNCTIONS  (same logic as original, extracted so a thread can call)
# ==============================================================================

def setup_database(db_name):
    """Builds the population table and index if they don't exist yet."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    columns_sql = "composite_id TEXT PRIMARY KEY, "
    columns_sql += ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])

    cursor.execute(f"CREATE TABLE IF NOT EXISTS population ({columns_sql})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")

    conn.commit()
    conn.close()


def ingest_to_vault(input_csv, db_name):
    """
    Reads one CSV file and writes it to one SQLite database.
    Entirely self-contained — safe to call from any thread.
    """
    setup_database(db_name)

    # Each thread opens its own connection.  sqlite3 connections are NOT
    # thread-safe to share, but creating one per thread is fine and fast.
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    cols_string = "composite_id, " + ", ".join([col.lower() for col in TARGET_COLUMNS])
    placeholders = "?, " + ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT OR IGNORE INTO population ({cols_string}) VALUES ({placeholders})"

    batch = []
    count = 0
    start_time = time.time()

    with open(input_csv, mode='r', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        for row in reader:
            serial = row.get('SERIAL', '').strip()
            pernum = row.get('PERNUM', '').strip()
            composite_id = f"{serial}_{pernum}"

            row_data = [composite_id]
            for col in TARGET_COLUMNS:
                try:
                    row_data.append(row.get(col, 'ERR123').strip())
                except Exception:
                    logging.warning(f"[{os.path.basename(input_csv)}] err: {col}")
                    row_data.append("ERR456")

            batch.append(tuple(row_data))
            count += 1

            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                ts = datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')
                logging.info(f"  [{os.path.basename(db_name)}]  {count:,} records  @  {ts}")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    conn.close()
    elapsed = round((time.time() - start_time) / 60, 2)
    logging.info(f"  [{os.path.basename(db_name)}]  DONE — {count:,} records in {elapsed} min.")
    return count, elapsed


# ==============================================================================
# THREAD WORKER
# Wraps ingest_to_vault with per-file stats so the main thread can report them.
# ==============================================================================

def process_file(filename, input_directory):
    """
    Called by the thread pool for each CSV file.
    Returns a dict with timing/stats so the main thread can print a summary.
    """
    file_path = os.path.join(input_directory, filename)
    yr = filename.split('-')[1].split('.')[0]
    db_name = r"D:\Data\Genealogy_Data\MasterVault_" + yr + ".db"

    logging.info(f"\n--- [{filename}]  Thread starting → {db_name} ---")

    wall_start = time.time()
    cpu_before = psutil.Process().cpu_times()
    snap_before = vault_stats.get_system_snapshot()

    record_count, elapsed_min = ingest_to_vault(file_path, db_name)

    wall_end = time.time()
    cpu_after = psutil.Process().cpu_times()
    snap_after = vault_stats.get_system_snapshot()

    vault_stats.print_stats_report(
        label=f"File: {filename}",
        before=snap_before,
        after=snap_after,
        wall_seconds=wall_end - wall_start,
        cpu_times_before=cpu_before,
        cpu_times_after=cpu_after,
    )

    dtime = wall_end - wall_start
    rec_per_sec = record_count / dtime
    logging.info(f"record_count : {record_count}")
    logging.info(f"dtime        : {dtime}")
    logging.info(f"recPerSec    : {rec_per_sec}")

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
    # ---- Set up logging FIRST so every line below goes to file + console ----
    vault_stats.setup_logging()

    vault_stats.print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_snap_before = vault_stats.get_system_snapshot()

    input_directory = r"D:\Data\Genealogy_Data\CSV"

    # Collect every CSV in the input directory
    csv_files = [f for f in os.listdir(input_directory) if f.endswith(".csv")]

    # --- NEW: cap the list if --files was specified ---
    if args.files is not None:
        csv_files = csv_files[:args.files]

    logging.info(f"\nFound {len(csv_files)} CSV file(s).  Launching up to {MAX_WORKERS} thread(s).\n")

    results = []

    # ThreadPoolExecutor works just like Java's ExecutorService.
    # submit() hands a job to the pool and returns a Future.
    # as_completed() yields each Future as it finishes (not in submission order).
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        # Submit all jobs up front; the pool throttles to MAX_WORKERS at a time
        future_to_file = {
            executor.submit(process_file, fname, input_directory): fname
            for fname in csv_files
        }

        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                result = future.result()  # re-raises any exception from the thread
                results.append(result)
            except Exception as exc:
                logging.error(f"\n!!! ERROR processing {fname}: {exc}")

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    logging.info("\n" + "=" * 60)
    logging.info(f"  THREAD SUMMARY   (MAX_WORKERS={MAX_WORKERS}, BATCH_SIZE={BATCH_SIZE:,})")
    logging.info("=" * 60)
    logging.info(f"  {'Year':<8}  {'Records':>12}  {'Minutes':>8}  {'File'}")
    logging.info(f"  {'-' * 8}  {'-' * 12}  {'-' * 8}  {'-' * 30}")

    for r in sorted(results, key=lambda x: x["year"]):
        logging.info(f"  {r['year']:<8}  {r['records']:>12,}  {r['elapsed_min']:>8.2f}  {r['filename']}")

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
    logging.info(f"\n  Total records across all files : {total_records:,}")
    logging.info(f"  Total wall-clock time          : {total_wall_min} minutes")
    logging.info(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    logging.info("")
