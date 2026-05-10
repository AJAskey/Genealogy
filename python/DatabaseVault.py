"""
-----------------------------------
File: DatabaseVault.py

Summary:

Design:

Inputs:

Outputs:

Comments for G:

--------------------------------

"""
"""
-----------------------------------
File: DatabaseVault.py

Summary: Creates a Database for each year of data.

Design:

Inputs: A csv file from IPUMS Containing all years of census data.

Outputs: An SQLite database file.


--------------------------------

"""

import csv
import datetime
import os
import sqlite3
import time

import psutil  # pip install psutil

# NOTE: This script does NOT use the GPU at all.
# SQLite + Python CSV work is 100% CPU and disk I/O.
# If you want GPU stats for other projects, look into pynvml (for NVIDIA cards).

# 1. DEFINE YOUR MASTER LIST OF VARIABLES
# We keep the core identifiers, names, and ages, plus EVERY target variable you parsed!
TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "PERNUM", "NUMPREC", "HHTYPE", "STATEICP", "COUNTYICP", "CITY", "FARM",
    "NMOTHERS", "NFATHERS", "PERWT", "FAMUNIT", "FAMSIZE", "MOMLOC", "POPLOC", "SPLOC", "NCHILD",
    "NSIBS", "ELDCH", "YNGCH", "RELATED", "SEX", "AGE", "BIRTHYR", "RACED", "BPLD",
    "NAMELAST", "NAMEFRST", "HISTID"]

import vault_stats


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
    batch_size = 500000
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

                try:
                    row_data.append(row.get(col, 'ERR123').strip())
                except:
                    print("err :", col)
                    row_data.append("ERR456")

            batch.append(tuple(row_data))
            count += 1

            # 3. Save to disk in batches
            if count % batch_size == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                clock_time = {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}
                print(f"Secured {count:,} fully enriched records...{clock_time}")

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
    vault_stats.print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_stats_before = vault_stats.get_system_snapshot()
    # -------------------------------------------------------------------------

    input_directory = r"D:\Data\Genealogy_Data\CSV"

    for filename in os.listdir(input_directory):
        if filename.endswith(".csv"):
            file_path = os.path.join(input_directory, filename)
            # Split by '-' -> ['census', '1910.csv']
            # Split the second part by '.' -> ['1910', 'csv']
            yr = filename.split('-')[1].split('.')[0]

            CSV_FILE = file_path
            DATABASE_NAME = r"D:\Data\Genealogy_Data\MasterVault_" + yr + ".db"

            print(f"\n--- Now processing: {filename} to {yr} ---")

            # ---- PER-FILE start ---------------------------------------------
            file_wall_start = time.time()
            file_cpu_before = psutil.Process().cpu_times()
            file_stats_before = vault_stats.get_system_snapshot()
            # -----------------------------------------------------------------

            ingest_to_vault(CSV_FILE, DATABASE_NAME)

            # ---- PER-FILE end -----------------------------------------------
            file_wall_end = time.time()
            file_cpu_after = psutil.Process().cpu_times()
            file_stats_after = vault_stats.get_system_snapshot()
            vault_stats.print_stats_report(
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
    session_stats_after = vault_stats.get_system_snapshot()
    vault_stats.print_stats_report(
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
