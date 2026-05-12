"""
-----------------------------------
File: DatabaseVault_threaded._onepy

Summary: Ingests all census CSV files into ONE shared SQLite database,
         using a thread pool so multiple CSV files are processed in parallel.

Design:  One thread per CSV file, up to MAX_WORKERS at a time.
         All threads write to the same database file, but each thread
         gets its own SQLite connection (WAL mode handles concurrency).

Changes from original:
  - 1 worker
  - 1 file at a time

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
# TUNING KNOBS
# ==============================================================================

MAX_WORKERS = 1
BATCH_SIZE = 500_000

# ==============================================================================
# >>> SINGLE DATABASE PATH  ← change this to wherever you want the file <<<
# ==============================================================================

MASTER_DB_PATH = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"

# ==============================================================================
# COLUMNS
# ==============================================================================

TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "NUMPREC", "PERNUM", "HHTYPE", "STATEICP", "COUNTYICP", "CITY",
    "FARM", "SEX", "AGE", "BIRTHYR", "NMOTHERS", "NFATHERS", "FAMUNIT", "FAMSIZE", "MOMLOC", "MOMRULE_HIST", "POPLOC",
    "POPRULE_HIST", "SPLOC", "SPRULE_HIST", "NCHILD", "NSIBS", "ELDCH", "YNGCH", "RELATED", "RACED", "BPLD", "NAMELAST",
    "NAMEFRST", "HISTID", "MBPLSTR"]


# ==============================================================================
# DATABASE SETUP  — called ONCE at startup, not per thread
# ==============================================================================


def setup_database(db_path):
    """
    Creates the population table and index in the single master database.
    Safe to call multiple times — IF NOT EXISTS protects against duplicates.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable WAL mode so multiple threads can write without stomping on each other
    cursor.execute("PRAGMA journal_mode=WAL")

    columns_sql = "composite_id TEXT PRIMARY KEY, "
    columns_sql += ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])

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
    """
    conn = sqlite3.connect(db_path)

    # WAL mode per connection too, just to be safe
    conn.execute("PRAGMA journal_mode=WAL")

    cursor = conn.cursor()

    cols_string = "composite_id, " + ", ".join([col.lower() for col in TARGET_COLUMNS])
    placeholders = "?, " + ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT OR IGNORE INTO population ({cols_string}) VALUES ({placeholders})"

    batch = []
    count = 0
    start_time = time.time()

    with open(input_csv, mode='r', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        # Figure out which TARGET_COLUMNS actually exist in THIS csv file.
        # Any column missing from the file will just get None (stored as NULL).
        available_cols = set(reader.fieldnames) if reader.fieldnames else set()

        for row in reader:
            serial = row.get('SERIAL', '').strip()
            pernum = row.get('PERNUM', '').strip()

            # Include the year in the composite_id so records from different
            # census years never collide even if SERIAL/PERNUM repeat.
            year = row.get('YEAR', 'UNKN').strip()
            composite_id = f"{year}_{serial}_{pernum}"

            row_data = [composite_id]
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
            count += 1

            if count % BATCH_SIZE == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                ts = datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')
                logging.info(f"  [{os.path.basename(input_csv)}]  {count:,} records  @  {ts}")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

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
    All files now write to the same MASTER_DB_PATH.
    """
    file_path = os.path.join(input_directory, filename)

    logging.info(f"\n--- [{filename}]  Thread starting → {MASTER_DB_PATH} ---")

    wall_start = time.time()
    cpu_before = psutil.Process().cpu_times()
    snap_before = vault_stats.get_system_snapshot()

    record_count, elapsed_min = ingest_to_vault(file_path, MASTER_DB_PATH)

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

    dtime = (wall_end - wall_start) * 1000
    rec_per_sec = record_count / dtime if dtime > 0 else 0
    logging.info(f"   record_count        : {record_count}")
    logging.info(f"   dtime milliseconds  : {dtime}")
    logging.info(f"   Rec per MS          : {rec_per_sec}\n")

    yr = filename.split('-')[1].split('.')[0] if '-' in filename else 'unknown'

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

    parser = argparse.ArgumentParser(description="Ingest census CSVs into a single SQLite vault.")
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

    vault_stats.setup_logging()
    vault_stats.print_session_header()

    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_snap_before = vault_stats.get_system_snapshot()

    # ---- Set up the ONE database before any threads start ----
    setup_database(MASTER_DB_PATH)

    input_directory = r"E:\Census\IPUMS\Original"

    csv_files = [f for f in os.listdir(input_directory) if f.endswith(".csv")]

    if args.files is not None:
        csv_files = csv_files[:args.files]

    logging.info(f"input_directory  {input_directory} \n")
    logging.info(f"Master database  {MASTER_DB_PATH} \n")
    logging.info(f"\nFound {len(csv_files)} CSV file(s).  Launching up to {MAX_WORKERS} thread(s).\n")

    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        future_to_file = {
            executor.submit(process_file, fname, input_directory): fname
            for fname in csv_files
        }

        for future in as_completed(future_to_file):
            fname = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                logging.error(f"\n!!! ERROR processing {fname}: {exc}")

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    logging.info("\n" + "=" * 60)
    logging.info(f"  THREAD SUMMARY   (MAX_WORKERS={MAX_WORKERS}, BATCH_SIZE={BATCH_SIZE:,})")
    logging.info("=" * 60)
    logging.info(f"  {'Year':<8}  {'Records':>12}  {'Minutes':>8} {'Rec_per_MS':>11}  {'File'}")
    logging.info(f"  {'-' * 8}  {'-' * 12}  {'-' * 8}  {'-' * 30}")

    for r in sorted(results, key=lambda x: x["year"]):
        ms = r["elapsed_min"] * 60_000.0
        rec_per_ms = r["records"] / ms if ms > 0 else 0.0
        logging.info(
            f"  {r['year']:<8}  {r['records']:>12,}  {r['elapsed_min']:>8.2f}  {rec_per_ms:>10.2f}  {r['filename']}")

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
