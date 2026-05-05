import csv
import datetime
import os
import re
import sqlite3
import time

import psutil

import statistics

# Columns to extract from each CSV and store in the database.
TARGET_COLUMNS = [
    "YEAR", "SAMPLE", "SERIAL", "NUMPREC", "HHTYPE", "STATEICP", "COUNTYICP", "CITY",
    "NMOTHERS", "NFATHERS","STREET", "PERNUM",  "FAMUNIT", "FAMSIZE",
    "MOMLOC", "POPLOC", "SPLOC", "NCHILD", "NSIBS", "ELDCH", "YNGCH", "RELATE", "RELATED", "SEX", "AGE", "BIRTHYR",
    "RACE", "RACED", "BPL", "BPLD", "NAMELAST", "NAMEFRST", "HISTID", "REEL", "PAGENO", "LINE", "MICROSEQ"]


def setup_database(db_name):
    """
    Set up the SQLite database with the population table and index.
    """
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Create table with columns from TARGET_COLUMNS
        columns_sql = ", ".join([f"{col.lower()} TEXT" for col in TARGET_COLUMNS])
        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS population (
                composite_id TEXT PRIMARY KEY,
                {columns_sql}
            )
        """
        cursor.execute(create_table_sql)

        # Create index on NAMELAST
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_last_name ON population (namelast)")

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False


def ingest_to_vault(input_csv, db_name):
    """
    Read CSV file and insert data into SQLite database.
    """
    # Check if database can be set up
    if not setup_database(db_name):
        return False

    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Prepare SQL statement
        placeholders = ", ".join(["?"] * len(TARGET_COLUMNS))
        insert_sql = f"""
            INSERT OR IGNORE INTO population (
                composite_id, {", ".join(TARGET_COLUMNS)}
            ) VALUES (?, {placeholders})
        """

        batch_size = 10000  # Reduced from 100000 to 10000 for better memory usage
        batch = []
        count = 0
        start_time = time.time()

        with open(input_csv, mode='r', encoding='utf-8', errors='replace') as infile:
            reader = csv.DictReader(infile, delimiter=',')

            # Verify required columns are present
            missing_cols = [col for col in TARGET_COLUMNS if col not in reader.fieldnames]
            if missing_cols:
                print(f"WARNING: Missing columns in {input_csv}: {missing_cols}")
                # Continue but skip these columns

            for row in reader:
                try:
                    # Build composite_id from SERIAL and PERNUM
                    serial = row.get('SERIAL', '').strip()
                    pernum = row.get('PERNUM', '').strip()
                    composite_id = f"{serial}_{pernum}"

                    # Prepare values for insertion
                    values = [composite_id]
                    for col in TARGET_COLUMNS:
                        # Use empty string if column missing
                        value = row.get(col, '') if col in reader.fieldnames else ''
                        values.append(value.strip())

                    # Add to batch
                    batch.append(tuple(values))
                    count += 1

                    # Process batch
                    if len(batch) >= batch_size:
                        cursor.executemany(insert_sql, batch)
                        conn.commit()
                        batch = []

                except Exception as e:
                    print(f"Error processing row: {e}")
                    continue

            # Process remaining batch
            if batch:
                cursor.executemany(insert_sql, batch)
                conn.commit()

        conn.close()
        end_time = time.time()

        elapsed = round((time.time() - start_time) / 60, 2)
        print(f"\n  SUCCESS: {count:,} records loaded into {db_name}")
        print(f"  Time elapsed: {elapsed} minutes.")
        return True

    except FileNotFoundError:
        print(f"ERROR: {input_csv} not found")
        return False
    except csv.Error as e:
        print(f"CSV error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False


if __name__ == '__main__':
    input_directory = r"E:\Census\IPUMS\Original"

    # ---- SESSION-LEVEL start ------------------------------------------------
    statistics.print_session_header()
    session_wall_start = time.time()
    session_cpu_before = psutil.Process().cpu_times()
    session_stats_before = statistics.get_system_snapshot()
    # -------------------------------------------------------------------------

    # Process all CSV files in the directory
    for filename in os.listdir(input_directory):
        if filename.endswith(".csv"):
            match = re.search(r'(\d{4})', filename)

            if not match:
                print(f"Skipping {filename} - could not extract year from filename")
                continue

            yr = match.group(1)
            csv_file = os.path.join(input_directory, filename)
            database_name = rf"D:\Data\Genealogy_Data\MasterVault_{yr}.db"

            try:
                # ---- PER-FILE start ---------------------------------------------
                file_wall_start = time.time()
                file_cpu_before = psutil.Process().cpu_times()
                file_stats_before = statistics.get_system_snapshot()
                # -----------------------------------------------------------------

                print(f"\n=== Processing {filename} ===")

                # ---- PER-FILE end -----------------------------------------------
                file_wall_end = time.time()
                file_cpu_after = psutil.Process().cpu_times()
                file_stats_after = statistics.get_system_snapshot()
                statistics.print_stats_report(
                    label=f"File: {filename}",
                    before=file_stats_before,
                    after=file_stats_after,
                    wall_seconds=file_wall_end - file_wall_start,
                    cpu_times_before=file_cpu_before,
                    cpu_times_after=file_cpu_after,
                )
                # -----------------------------------------------------------------

                if ingest_to_vault(csv_file, database_name):
                    print(f"Successfully processed {filename}")
                else:
                    print(f"Failed to process {filename}")
            except Exception as e:
                print(f"Error processing {filename}: {str(e)}")
                continue

            # ---- SESSION-LEVEL end --------------------------------------------------
            session_wall_end = time.time()

            session_cpu_after = psutil.Process().cpu_times()
            session_stats_after = statistics.get_system_snapshot()
            statistics.print_stats_report(
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

    print(f"  Session ended: {datetime.datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print()
    # -------------------------------------------------------------------------

print("\n=== All vaults complete ===")
