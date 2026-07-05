"""
-----------------------------------
File: BuildVaultHashes.py

Summary: Standalone overnight process to calculate deterministic
         demographic hashes for all records in the SQLite Vaults.
         Separated from ingestion due to extensive compute times.
-----------------------------------
"""

import os
import sqlite3
import sys
import time

# Pathing for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Use an environment variable for the base data directory to allow for easy switching
# between machines (Windows dev, Linux build) without code changes.
# Defaults to D:\Data\Genealogy_Data if the variable is not set.
BASE_DATA_DIR = os.getenv('GENEALOGY_DATA_DIR', r"D:\Data\Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")


def build_computed_hashes(vault_dir, logger):
    logger.info("Generating computed Data Vault keys (dem_hash & family_hash)...")

    for filename in os.listdir(vault_dir):
        if not (filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename):
            continue

        db_path = os.path.join(vault_dir, filename)
        logger.info(f"  -> Computing hashes for {filename}...")

        start_time = time.time()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Turbo-charge SQLite for massive bulk inserts
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = OFF;")
            cursor.execute("PRAGMA cache_size = -2000000;")  # Give it 2GB of RAM cache
            cursor.execute("PRAGMA temp_store = MEMORY;")

            # DECISION: Drop tables to ensure a clean slate and prevent schema conflicts from partial runs.
            cursor.execute("DROP TABLE IF EXISTS computed_ind_hashes")
            cursor.execute("DROP TABLE IF EXISTS computed_fam_hashes")
            cursor.execute("CREATE TABLE computed_ind_hashes (histid TEXT PRIMARY KEY, dem_hash TEXT)")
            cursor.execute(
                "CREATE TABLE computed_fam_hashes (family_id TEXT PRIMARY KEY, family_hash TEXT, snapshot_fam_hash TEXT)")

            # SQLite uses '/' for integer division
            cursor.execute("""
                           INSERT
                           OR IGNORE INTO computed_ind_hashes (histid, dem_hash)
                           SELECT histid,
                                  TRIM(CAST(birthyr AS TEXT)) || '|' ||
                                  TRIM(CAST(sex AS TEXT)) || '|' ||
                                  COALESCE(TRIM(CAST(raced AS TEXT)), '0') || '|' ||
                                  CAST(CASE
                                           WHEN CAST(bpld AS INTEGER) >= 1000 THEN CAST(bpld AS INTEGER) / 100
                                           ELSE CAST(bpld AS INTEGER) END AS TEXT) || '|' ||
                                  COALESCE(CAST(CASE
                                                    WHEN CAST(fbpl AS INTEGER) >= 1000 THEN CAST(fbpl AS INTEGER) / 100
                                                    ELSE CAST(fbpl AS INTEGER) END AS TEXT), '0') || '|' ||
                                  COALESCE(CAST(CASE
                                                    WHEN CAST(mbpl AS INTEGER) >= 1000 THEN CAST(mbpl AS INTEGER) / 100
                                                    ELSE CAST(mbpl AS INTEGER) END AS TEXT), '0') || '|' ||
                                  '000' || '|' || '000'
                           FROM individuals
                           """)
            cursor.execute("""
                           INSERT
                           OR IGNORE INTO computed_fam_hashes (family_id, family_hash, snapshot_fam_hash)
                           SELECT f.family_id,
                                  h.dem_hash || '-SP-' || COALESCE(s.dem_hash, 'NONE'),
                                  h.dem_hash || '-SP-' || COALESCE(s.dem_hash, 'NONE') || '-KIDS-' ||
                                  COALESCE(CAST(f.kids_byr_sum AS TEXT), '0')
                           FROM families f
                                    JOIN computed_ind_hashes h ON f.head_histid = h.histid
                                    LEFT JOIN computed_ind_hashes s ON f.spouse_histid = s.histid
                           """)

        elapsed = round((time.time() - start_time) / 60, 2)
        logger.info(f"     [DONE] {filename} completed in {elapsed} minutes.")


def build_indices(vault_dir, logger):
    logger.info("Building database indices for downstream queries... (This may take a while)")
    for filename in os.listdir(vault_dir):
        if not (filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename):
            continue

        db_path = os.path.join(vault_dir, filename)
        logger.info(f"  -> Indexing {filename}...")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Turbo-charge index building
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = OFF;")
            cursor.execute("PRAGMA cache_size = -2000000;")
            cursor.execute("PRAGMA temp_store = MEMORY;")
            
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_individuals_parents ON individuals(father_histid, mother_histid);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_year_serial ON families(year, serial);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_family ON individuals(family_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_head ON families(head_histid);")
    logger.info("Indices built successfully!")


if __name__ == '__main__':
    logger = gen_logging.setup_logging('HashBuilder')
    logger.info("=====================================================================")
    logger.info("  STANDALONE VAULT HASH & INDEX BUILDER")
    logger.info("=====================================================================")
    logger.info(f"Target Vaults Directory: {VAULT_DIR}")
    logger.info("=====================================================================")
    build_computed_hashes(VAULT_DIR, logger)
    build_indices(VAULT_DIR, logger)
    logger.info("\nAll hashes and indices computed successfully!")
