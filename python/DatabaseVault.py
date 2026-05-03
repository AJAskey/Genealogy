"""
-----------------------------------
File: DatabaseVault.py

Summary: Creates a SQLite database for each decade of IPUMS census data.

Design:  Loops over all CSV files in the input directory. For each file,
         extracts the census year from the filename, creates a decade-specific
         SQLite database, and loads all records in batches of 100,000 for
         memory efficiency. A composite key (SERIAL_PERNUM) prevents duplicate
         records on re-runs. An index on NAMELAST keeps name searches fast.

Inputs:  CSV files from IPUMS full-count census downloads.
         Expected filename format: census-YYYY.csv
         Expected location: E:\Census\IPUMS\Original\

Outputs: One SQLite database per census year.
         Expected location: D:\Data\Genealogy_Data\MasterVault_YYYY.db

--------------------------------
"""

import csv
import os
import re
import sqlite3
import time

# Columns to extract from each CSV and store in the database.
# These map directly to IPUMS variable names.
# SERIAL + PERNUM form the unique person key within a census year.
TARGET_COLUMNS = [
    "SERIAL", "PERNUM", "NAMEFRST", "NAMELAST", "AGE", "BIRTHYR",
    "MOMLOC", "POPLOC", "REGION", "STATEICP", "COUNTYICP", "METAREA",
    "CITY", "CITYPOP", "METDIST", "CITYMETD", "GQ", "SFTYPE", "SFRELATE",
    "STEPMOM", "STEPPOP", "SPRULE_HIST", "RELATE", "RELATED", "SEX",
    "RACE", "RACED", "BPL", "BPLD", "CITIZEN", "MTONGUE", "MTONGUED",
    "HISPRULE", "HIGRADE", "HIGRADED", "EDUC", "EDUCD", "EMPSTAT",
    "EMPSTATD", "LABFORCE", "CLASSWKR", "CLASSWKRD", "VERSIONHIST",
    "VETSTAT", "VETSTATD"
]

def setup_database(db_name):
    """
    Creates the population table and name index if they do not already exist.
    Schema is built dynamically from TARGET_COLUMNS so adding a column
    only requires updating that list.
    """
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
    Reads input_csv and loads all records into the SQLite database at db_name.
    Records are inserted in batches for memory efficiency.
    Duplicate records (same SERIAL + PERNUM) are silently ignored so the
    function is safe to re-run against an existing database.
    """
    setup_database(db_name)

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

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
            serial = row.get('SERIAL', '').strip()
            pernum = row.get('PERNUM', '').strip()
            composite_id = f"{serial}_{pernum}"

            row_data = [composite_id]
            for col in TARGET_COLUMNS:
                row_data.append(row.get(col, '').strip())

            batch.append(tuple(row_data))
            count += 1

            if count % batch_size == 0:
                cursor.executemany(insert_query, batch)
                conn.commit()
                batch = []
                print(f"  Loaded {count:,} records...")

        if batch:
            cursor.executemany(insert_query, batch)
            conn.commit()

    conn.close()

    elapsed = round((time.time() - start_time) / 60, 2)
    print(f"\n  SUCCESS: {count:,} records loaded into {db_name}")
    print(f"  Time elapsed: {elapsed} minutes.")


if __name__ == '__main__':

    input_directory = r"E:\Census\IPUMS\Original"

    for filename in os.listdir(input_directory):
        if filename.endswith(".csv"):

            match = re.search(r'(\d{4})', filename)
            if not match:
                print(f"Skipping {filename} - could not extract year from filename")
                continue

            yr = match.group(1)
            csv_file = os.path.join(input_directory, filename)
            database_name = rf"D:\Data\Genealogy_Data\MasterVault_{yr}.db"

            print(f"\n--- Processing: {filename} -> MasterVault_{yr}.db ---")
            ingest_to_vault(csv_file, database_name)

    print("\n--- All vaults complete ---")
