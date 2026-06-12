"""
-----------------------------------
File: CreateYearlyVaults.py

Summary: A utility script that reads the master relational vault and exports
         smaller, self-contained, single-year databases. This makes manual
         browsing and ad-hoc queries much faster and more manageable.

Design:
  - Connects to the monolithic MasterVault_Relational.db.
  - Gets a distinct list of all census years present in the data.
  - For each year, it creates a new database (e.g., YearVault_1880.db)
    and copies only the families and individuals from that specific year.

Architect & Designer: Andy Askey
Coders (AI Assistants): Google Gemini, Anthropic Claude, Gemini Code Assist

License: Apache License 2.0
http://www.apache.org/licenses/LICENSE-2.0

GitHub Open Source Project: /https://github.com/AJAskey/Genealogy

-----------------------------------
"""

import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
for p in [os.path.join(project_root, 'python'), project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# --- Configuration ---
if os.name == 'nt':
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MASTER_DB = os.path.join(BASE_DATA_DIR, "MasterVault_Relational.db")
OUTPUT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")


def create_yearly_vaults(logger):
    logger.info(f"Reading from Master Vault: {MASTER_DB}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with sqlite3.connect(MASTER_DB) as conn:
        cursor = conn.cursor()
        logger.info("Finding all distinct census years in the master database...")
        cursor.execute("SELECT DISTINCT year FROM families ORDER BY year")
        years = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found years: {years}")

    for year in years:
        yearly_db_path = os.path.join(OUTPUT_DIR, f"YearVault_{year}.db")
        logger.info(f"Creating partitioned vault for {year} at: {yearly_db_path}")

        # Use ATTACH in a single connection to perform a high-speed data transfer
        with sqlite3.connect(yearly_db_path) as yearly_conn:
            yearly_conn.execute(f"ATTACH DATABASE '{MASTER_DB}' AS master;")
            yearly_conn.execute(f"CREATE TABLE families AS SELECT * FROM master.families WHERE year = {year};")
            yearly_conn.execute(f"CREATE TABLE individuals AS SELECT * FROM master.individuals WHERE year = {year};")
            yearly_conn.execute("DETACH DATABASE master;")

            # Add indices to make browsing in DB Browser instantaneous
            logger.info(f"  -> Building indices for {year}...")
            yearly_conn.execute("CREATE INDEX idx_individuals_parents ON individuals(father_histid, mother_histid);")
            yearly_conn.execute("CREATE INDEX idx_individuals_names ON individuals(last_name, first_name);")
            yearly_conn.execute("CREATE INDEX idx_families_year_serial ON families(year, serial);")
        logger.info(f"Successfully created vault for {year}.")

    logger.info("\nAll yearly vaults have been created successfully!")


if __name__ == "__main__":
    main_logger = gen_logging.setup_logging(logger_name="YEARLY_VAULT_CREATOR")
    create_yearly_vaults(main_logger)
