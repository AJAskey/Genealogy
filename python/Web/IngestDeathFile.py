"""
-----------------------------------
File: IngestDeathFile.py

Summary: Parses pipe-delimited death index files (e.g., from Reclaim the Records)
         and securely loads them into the DeathIndexVault.db.
         
         Extracts First Name, Last Name, Birth Dates, Death Dates, and saves 
         the Social Security Number (SSN) as a future deterministic linking key.
-----------------------------------
"""

import csv
import os
import sqlite3
import sys

# 1 Add the 'python' directory to sys.path so we can import from 'utils'
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.abspath(os.path.join(script_dir, '..'))
if python_dir not in sys.path:
    sys.path.append(python_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# 2. Step up two folder levels ('..') to reach the main project root
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))

INPUT_DIR = os.path.join(project_root, "data/deaths")

if os.name == 'nt':
    DEATH_DB = r"D:\Data\Genealogy_Data\DeathIndexVault.db"
else:
    DEATH_DB = os.path.expanduser("~/Genealogy_Data/DeathIndexVault.db")


def safe_int(val):
    """Converts a string to an integer, returning None if invalid or '99'/'9999'."""
    val = str(val).strip()
    if not val or val in ('99', '9999', '999900'):
        return None
    try:
        return int(val)
    except ValueError:
        return None


def clean_ssn(val):
    """Cleans SSN strings and converts dummy values (999s, 000s) to None."""
    if not val:
        return None
    val = str(val).strip().replace('-', '')
    if not val or val in ('999999999', '000000000'):
        return None
    return val


# ==============================================================================
# ADAPTER 1: Reclaim The Records (Pipe-Delimited)
# ==============================================================================
def parse_reclaim_pipe_file(filepath):
    """Generator that yields standard dictionary records from a pipe file."""
    filename = os.path.basename(filepath)
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        header = f.readline()
        for line in f:
            parts = line.split('|')
            if len(parts) < 32:
                continue

            cert_id = parts[0].strip()
            ssn = clean_ssn(parts[18])

            yield {
                "record_id": f"{filename}_{cert_id}",  # Collision-Proof ID!
                "source_file": filename,
                "first_name": " ".join(parts[1].split()),
                "last_name": " ".join(parts[2].split()),
                "death_month": safe_int(parts[3]),
                "death_day": safe_int(parts[4]),
                "death_year": safe_int(parts[5]),
                "birth_month": safe_int(parts[29]),
                "birth_day": safe_int(parts[30]),
                "birth_year": safe_int(parts[31]),
                "ssn": ssn
            }


# ==============================================================================
# ADAPTER 2: Reclaim The Records (Broken CSV Format)
# ==============================================================================
def parse_reclaim_csv_file(filepath):
    """Generator that uses relative anchoring to parse misaligned CSV files."""
    filename = os.path.basename(filepath)
    suffixes = {'SR', 'JR', 'I', 'II', 'III', 'IV'}

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 32:
                continue

            # Find the Death Year to anchor the rest of the columns
            death_year_idx = -1
            for i in range(3, min(9, len(parts))):
                if len(parts[i]) == 4 and parts[i].isdigit() and (
                        parts[i].startswith('19') or parts[i].startswith('20')):
                    death_year_idx = i
                    break

            if death_year_idx == -1:
                continue  # Could not reliably parse this row

            cert_id = parts[0].strip()

            # Parse Name safely
            name_parts = [p.strip() for p in parts[1:death_year_idx - 2] if p.strip()]
            first_name, last_name = "", ""

            if len(name_parts) == 1:
                last_name = name_parts[0]
            elif len(name_parts) == 2:
                first_name, last_name = name_parts[0], name_parts[1]
            elif len(name_parts) > 2:
                if name_parts[-1].upper() in suffixes:
                    last_name = f"{name_parts[-2]} {name_parts[-1]}"
                    first_name = " ".join(name_parts[:-2])
                else:
                    last_name = name_parts[-1]
                    first_name = " ".join(name_parts[:-1])

            try:
                ssn = clean_ssn(parts[death_year_idx + 13])
                yield {
                    "record_id": f"{filename}_{cert_id}",
                    "source_file": filename,
                    "first_name": first_name,
                    "last_name": last_name,
                    "death_month": safe_int(parts[death_year_idx - 2]),
                    "death_day": safe_int(parts[death_year_idx - 1]),
                    "death_year": safe_int(parts[death_year_idx]),
                    "birth_month": safe_int(parts[death_year_idx + 24]),
                    "birth_day": safe_int(parts[death_year_idx + 25]),
                    "birth_year": safe_int(parts[death_year_idx + 26]),
                    "ssn": ssn
                }
            except IndexError:
                continue  # Skip malformed rows


# ==============================================================================
# ADAPTER 3: Nebraska (Standard CSV format)
# ==============================================================================
def parse_nebraska_csv_file(filepath):
    """Generator to parse clean, standard CSV files using Python's CSV module."""
    filename = os.path.basename(filepath)

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cert_id = str(row.get("State File #", "")).strip()
            if not cert_id:
                continue

            # Combine First and Middle names safely
            first = str(row.get("First Name", "")).strip()
            middle = str(row.get("Middle", "")).strip()
            first_name = f"{first} {middle}".strip()

            # Parse the MM/DD/YYYY death date
            death_date_str = str(row.get("Death Date", "")).strip()
            d_month, d_day, d_year = None, None, None
            if death_date_str and "/" in death_date_str:
                d_parts = death_date_str.split("/")
                if len(d_parts) == 3:
                    d_month = safe_int(d_parts[0])
                    d_day = safe_int(d_parts[1])
                    d_year = safe_int(d_parts[2])

            yield {
                "record_id": f"{filename}_{cert_id}",
                "source_file": filename,
                "first_name": first_name,
                "last_name": str(row.get("Last Name", "")).strip(),
                "death_month": d_month,
                "death_day": d_day,
                "death_year": d_year,
                "birth_month": None,
                "birth_day": None,
                "birth_year": None,
                "ssn": None
            }


# ==============================================================================
# ADAPTER 4: Missouri (Missing Cert ID)
# ==============================================================================
def parse_missouri_csv_file(filepath):
    """Generator to parse Missouri CSV files which lack a specific Certificate ID."""
    filename = os.path.basename(filepath)

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            first = str(row.get("FIRST NAME", "")).strip()
            middle = str(row.get("MIDDLE INITIAL", "")).strip()
            first_name = f"{first} {middle}".strip()

            death_date_str = str(row.get("DATE OF DEATH", "")).strip()
            d_month, d_day, d_year = None, None, None
            if death_date_str and "/" in death_date_str:
                d_parts = death_date_str.split("/")
                if len(d_parts) == 3:
                    d_month = safe_int(d_parts[0])
                    d_day = safe_int(d_parts[1])
                    d_year = safe_int(d_parts[2])

            yield {
                "record_id": f"{filename}_row_{reader.line_num}",  # Auto-generate ID from line number
                "source_file": filename,
                "first_name": first_name,
                "last_name": str(row.get("LAST NAME", "")).strip(),
                "death_month": d_month,
                "death_day": d_day,
                "death_year": d_year,
                "birth_month": None,
                "birth_day": None,
                "birth_year": None,
                "ssn": None
            }


# ==============================================================================
# THE UNIVERSAL LOADER
# ==============================================================================
def ingest_death_directory(logger):
    if not os.path.exists(INPUT_DIR):
        logger.error(f"Cannot find input directory: {INPUT_DIR}")
        return

    logger.info(f"Connecting to Death Index Vault: {DEATH_DB}")
    os.makedirs(os.path.dirname(DEATH_DB), exist_ok=True)

    with sqlite3.connect(DEATH_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")

        # Upgraded table with collision-proof ID and source file tracking
        conn.execute('''
                     CREATE TABLE IF NOT EXISTS universal_death_index
                     (
                         record_id
                         TEXT
                         PRIMARY
                         KEY,
                         source_file
                         TEXT,
                         first_name
                         TEXT,
                         last_name
                         TEXT,
                         death_year
                         INTEGER,
                         death_month
                         INTEGER,
                         death_day
                         INTEGER,
                         birth_year
                         INTEGER,
                         birth_month
                         INTEGER,
                         birth_day
                         INTEGER,
                         ssn
                         TEXT
                     )
                     ''')

        total_inserted = 0

        # Scan the directory for all txt files
        for file in os.listdir(INPUT_DIR):
            filepath = os.path.join(INPUT_DIR, file)

            # Determine which adapter to use based on file extension & header
            if file.lower().endswith(".txt"):
                parser_func = parse_reclaim_pipe_file
            elif file.lower().endswith(".csv"):
                # Peek at the header to see what kind of CSV it is
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    header = f.readline()
                    header_upper = header.upper()

                if "STATE FILE #" in header_upper and "COUNTY" in header_upper:
                    parser_func = parse_nebraska_csv_file
                elif "DATE OF DEATH" in header_upper and "MIDDLE INITIAL" in header_upper:
                    parser_func = parse_missouri_csv_file
                else:
                    parser_func = parse_reclaim_csv_file
            else:
                continue

            logger.info(f"\nProcessing file: {file}")

            batch = []
            file_count = 0

            for record in parser_func(filepath):
                if file_count < 3:
                    logger.info(
                        f"  [SAMPLE] {record['first_name']} {record['last_name']} | Born: {record['birth_year']} | Died: {record['death_year']} | SSN: {record['ssn']}")

                batch.append((
                    record["record_id"], record["source_file"], record["first_name"], record["last_name"],
                    record["death_year"], record["death_month"], record["death_day"],
                    record["birth_year"], record["birth_month"], record["birth_day"], record["ssn"]
                ))
                file_count += 1

                if file_count % 100_000 == 0:
                    conn.executemany(
                        "INSERT OR IGNORE INTO universal_death_index VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
                    batch = []
                    logger.info(f"  -> Inserted {file_count:,} records from {file}...")

            if batch:
                conn.executemany("INSERT OR IGNORE INTO universal_death_index VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 batch)

            # Force SQLite to save this file's data to the hard drive immediately!
            conn.commit()
            logger.info(f"Finished {file} - Parsed {file_count:,} lines of text.")
            total_inserted += file_count

        actual_count = conn.execute("SELECT COUNT(*) FROM universal_death_index").fetchone()[0]
        logger.info(f"\nSUCCESS! Mass-Ingestion complete.")
        logger.info(f"Total lines of text parsed: {total_inserted:,}")
        logger.info(f"Actual UNIQUE records safely locked in Database: {actual_count:,}")


def main():
    """Main entry point for Death File Ingestion."""
    main_logger = gen_logging.setup_logging(logger_name="DEATH_INGEST")
    ingest_death_directory(main_logger)


if __name__ == "__main__":
    main()
