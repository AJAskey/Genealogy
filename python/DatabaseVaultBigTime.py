"""
-----------------------------------
File: DatabaseVaultBigTime.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""
"""
-----------------------------------
File: DatabaseVaultBigTime.py

Summary: Creates a Database for each year of data.

Design:

Inputs: A csv file from IPUMS Containing all years of census data.

Outputs: An SQLite database file.


--------------------------------

"""

import csv
import datetime
import os
import platform
import sqlite3
import time

import psutil  # pip install psutil

# NOTE: This script does NOT use the GPU at all.
# SQLite + Python CSV work is 100% CPU and disk I/O.
# If you want GPU stats for other projects, look into pynvml (for NVIDIA cards).

# 1. DEFINE YOUR MASTER LIST OF VARIABLES
# We keep the core identifiers, names, and ages, plus EVERY target variable you parsed!
TARGET_COLUMNS = ["YEAR",
                  "SERIAL", "PERNUM", "NAMEFRST", "NAMELAST", "AGE", "BIRTHYR", "MOMLOC", "POPLOC",
                  "STATEICP", "COUNTYICP", "CITY",
                  "NFATHERS", "NCHILD", "NSIBS", "FAMSIZE",
                  "RELATED", "SEX", "RACED", "BPLD"
                  ]


# ==============================================================================
# STATS HELPERS
# ==============================================================================

def get_system_snapshot():
    """Capture a point-in-time snapshot of CPU, memory, and disk."""
    snapshot = {}

    # CPU
    snapshot['cpu_percent'] = psutil.cpu_percent(interval=1)
    snapshot['cpu_count_logical'] = psutil.cpu_count(logical=True)
    snapshot['cpu_count_physical'] = psutil.cpu_count(logical=False)

    # Memory (RAM)
    mem = psutil.virtual_memory()
    snapshot['ram_total_gb'] = mem.total / (1024 ** 3)
    snapshot['ram_used_gb'] = mem.used / (1024 ** 3)
    snapshot['ram_available_gb'] = mem.available / (1024 ** 3)
    snapshot['ram_percent'] = mem.percent

    # Swap (Windows calls this "page file"; same idea)
    swap = psutil.swap_memory()
    snapshot['swap_total_gb'] = swap.total / (1024 ** 3)
    snapshot['swap_used_gb'] = swap.used / (1024 ** 3)
    snapshot['swap_percent'] = swap.percent

    # Disk for the D: drive where the databases live
    try:
        disk = psutil.disk_usage(r'D:\\')
        snapshot['disk_d_total_gb'] = disk.total / (1024 ** 3)
        snapshot['disk_d_used_gb'] = disk.used / (1024 ** 3)
        snapshot['disk_d_free_gb'] = disk.free / (1024 ** 3)
        snapshot['disk_d_percent'] = disk.percent
    except Exception:
        snapshot['disk_d_total_gb'] = None  # drive not present on this machine

    return snapshot


def print_session_header():
    """Print a banner at the very top with machine info and start time."""
    print("=" * 65)
    print("  DATABASE VAULT  —  SESSION START")
    print("=" * 65)
    print(f"  Started   : {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Machine   : {platform.node()}")
    print(f"  OS        : {platform.system()} {platform.release()} ({platform.version()})")
    print(f"  Python    : {platform.python_version()}")
    print(f"  CPU cores : {psutil.cpu_count(logical=False)} physical  /  "
          f"{psutil.cpu_count(logical=True)} logical")

    mem = psutil.virtual_memory()
    print(f"  Total RAM : {mem.total / (1024 ** 3):.1f} GB")

    swap = psutil.swap_memory()
    print(f"  Page file : {swap.total / (1024 ** 3):.1f} GB  (Windows swap / page file)")
    print(f"  GPU note  : SQLite + Python CSV is CPU + disk only — no GPU involvement.")
    print("=" * 65)
    print()


def print_stats_report(label, before, after, wall_seconds, cpu_times_before, cpu_times_after):
    """Print a nicely formatted before/after stats comparison."""

    cpu_user = cpu_times_after.user - cpu_times_before.user
    cpu_system = cpu_times_after.system - cpu_times_before.system
    cpu_total = cpu_user + cpu_system

    wall_min = wall_seconds / 60

    print()
    print("=" * 65)
    print(f"  STATS REPORT  —  {label}")
    print("=" * 65)

    print(f"\n  {'TIMING':}")
    print(f"    Wall clock elapsed : {wall_seconds:,.1f} sec  ({wall_min:.2f} min)")
    print(f"    CPU user time      : {cpu_user:,.1f} sec")
    print(f"    CPU system time    : {cpu_system:,.1f} sec")
    print(f"    CPU total time     : {cpu_total:,.1f} sec")
    print(f"    (CPU total > wall clock means multiple cores were used in parallel)")

    print(f"\n  {'CPU USAGE (during run)':}")
    print(f"    Start  : {before['cpu_percent']:.1f}%")
    print(f"    End    : {after['cpu_percent']:.1f}%")

    print(f"\n  {'MEMORY  (RAM)':}")
    print(f"    Start  used : {before['ram_used_gb']:.2f} GB  ({before['ram_percent']:.1f}%)")
    print(f"    End    used : {after['ram_used_gb']:.2f} GB  ({after['ram_percent']:.1f}%)")
    print(f"    Available   : {after['ram_available_gb']:.2f} GB remaining")

    print(f"\n  {'SWAP / PAGE FILE':}")
    if before['swap_total_gb'] > 0:
        print(f"    Total       : {before['swap_total_gb']:.2f} GB")
        print(f"    Start  used : {before['swap_used_gb']:.2f} GB  ({before['swap_percent']:.1f}%)")
        print(f"    End    used : {after['swap_used_gb']:.2f} GB  ({after['swap_percent']:.1f}%)")
    else:
        print(f"    (No swap / page file configured)")

    if before['disk_d_total_gb'] is not None:
        print(f"\n  {'DISK  (D: drive)':}")
        print(f"    Total       : {before['disk_d_total_gb']:.1f} GB")
        print(f"    Start  used : {before['disk_d_used_gb']:.1f} GB  ({before['disk_d_percent']:.1f}%)")
        print(f"    End    used : {after['disk_d_used_gb']:.1f} GB  ({after['disk_d_percent']:.1f}%)")
        delta_gb = after['disk_d_used_gb'] - before['disk_d_used_gb']
        print(f"    Space added : {delta_gb:+.2f} GB  (new database data written this run)")
        print(f"    Free now    : {after['disk_d_free_gb']:.1f} GB")

    print(f"\n  {'GPU':}")
    print(f"    Not applicable — SQLite/CSV work is CPU + disk I/O only.")
    print("=" * 65)
    print()


# ==============================================================================
# ORIGINAL DATABASE FUNCTIONS  (unchanged)
# ==============================================================================

def setup_database(db_name):
    """Dynamically builds the table based on your TARGET_COLUMNS."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # We always need the composite ID as the primary key
    columns_sql = "composite_id TEXT PRIMARY KEY, "

    # Add all the other columns as TEXT
    columns_sql += ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])

    cursor.execute(f"CREATE TABLE IF NOT EXISTS population ({columns_sql})")

    # Create an index on the last name so searches remain lightning fast!
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")

    conn.commit()
    conn.close()


def ingest_to_vault(input_csv, db_name):
    setup_database(db_name)
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Dynamically build the INSERT query
    cols_string = "composite_id, " + ", ".join([col.lower() for col in TARGET_COLUMNS])
    placeholders = "?, " + ", ".join(["?"] * len(TARGET_COLUMNS))
    insert_query = f"INSERT OR IGNORE INTO population ({cols_string}) VALUES ({placeholders})"

    batch = []
    batch_size = 100000
    count = 0
    start_time = time.time()

    with open(input_csv, mode='r', errors='replace') as infile:
        reader = csv.DictReader(infile, delimiter=',')

        for row in reader:
            # 1. Build the unique ID
            serial = row.get('SERIAL', '').strip()
            pernum = row.get('PERNUM', '').strip()
            composite_id = f"{serial}_{pernum}"

            # 2. Grab ALL requested data dynamically
            row_data = [composite_id]
            for col in TARGET_COLUMNS:
                row_data.append(row.get(col, '').strip())

            batch.append(tuple(row_data))
            count += 1

            # 3. Save to disk in batches
            if count % batch_size == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                print(f"Secured {count:,} fully enriched records...")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    conn.close()
    end_time = time.time()
    print(f"\nSUCCESS! {count:,} fully enriched records locked in {db_name}.")
    print(f"Time elapsed: {round((end_time - start_time) / 60, 2)} minutes.")


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == '__main__':

    # ---- SESSION-LEVEL start ------------------------------------------------
    print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_stats_before = get_system_snapshot()
    # -------------------------------------------------------------------------

    input_directory = r"E:\Census\IPUMS\Original"

    for filename in os.listdir(input_directory):
        if filename.endswith("usa_00035.csv"):
            file_path = os.path.join(input_directory, filename)
            # tmp = re.sub("usa_00032.csv", "0", file_path)
            yr = "1850-1900"

            CSV_FILE = file_path
            DATABASE_NAME = r"D:\Data\Genealogy_Data\MasterVault_" + yr + ".db"

            print(f"\n--- Now processing: {filename} to {yr} ---")

            # ---- PER-FILE start ---------------------------------------------
            file_wall_start = time.time()
            file_cpu_before = psutil.Process().cpu_times()
            file_stats_before = get_system_snapshot()
            # -----------------------------------------------------------------

            ingest_to_vault(CSV_FILE, DATABASE_NAME)

            # ---- PER-FILE end -----------------------------------------------
            file_wall_end = time.time()
            file_cpu_after = psutil.Process().cpu_times()
            file_stats_after = get_system_snapshot()
            print_stats_report(
                label=f"File: {filename}",
                before=file_stats_before,
                after=file_stats_after,
                wall_seconds=file_wall_end - file_wall_start,
                cpu_times_before=file_cpu_before,
                cpu_times_after=file_cpu_after,
            )
            # -----------------------------------------------------------------

    # ---- SESSION-LEVEL end --------------------------------------------------
    session_wall_end = time.time()
    session_cpu_after = psutil.Process().cpu_times()
    session_stats_after = get_system_snapshot()
    print_stats_report(
        label="FULL SESSION TOTAL",
        before=session_stats_before,
        after=session_stats_after,
        wall_seconds=session_wall_end - session_wall_start,
        cpu_times_before=session_cpu_before,
        cpu_times_after=session_cpu_after,
    )
    print(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print()
    # -------------------------------------------------------------------------
