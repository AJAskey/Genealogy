import gen_logging, os, sqlite3

"""
File: Fix_Missing_Table.py
Summary: Instantly builds the missing clan_details table in the Demographics database.
"""
import duckdb
import os

if os.name == 'nt':
    BASE_DATA_DIR = r"c:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

MATCH_DB_PATH = os.path.join(BASE_DATA_DIR, "DemographicMatches2.db")


def build_computed_hashes(vault_dir, logger):
    logger.info("Generating computed Data Vault keys (dem_hash & family_hash)...")
    for filename in os.listdir(vault_dir):

        if filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename: continue

        db_path = os.path.join(vault_dir, filename)
        logger.info(f"  -> Computing hashes for {filename}...")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS computed_ind_hashes (histid TEXT PRIMARY KEY, dem_hash TEXT)")
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS computed_fam_hashes (family_id TEXT PRIMARY KEY, family_hash TEXT)")

            # SQLite uses '/' for integer division
            cursor.execute("""
                           INSERT
                           OR IGNORE INTO computed_ind_hashes (histid, dem_hash)
                           SELECT histid,
                                  TRIM(CAST(birthyr AS TEXT)) || '|' ||
                                  TRIM(CAST(sex AS TEXT)) || '|' ||
                                  CAST(CASE
                                           WHEN CAST(bpld AS INTEGER) >= 1000 THEN CAST(bpld AS INTEGER) / 100
                                           ELSE CAST(bpld AS INTEGER) END AS TEXT) || '|' ||
                                  COALESCE(CAST(CASE
                                                    WHEN CAST(fbpl AS INTEGER) >= 1000 THEN CAST(fbpl AS INTEGER) / 100
                                                    ELSE CAST(fbpl AS INTEGER) END AS TEXT), '0') || '|' ||
                                  COALESCE(CAST(CASE
                                                    WHEN CAST(mbpl AS INTEGER) >= 1000 THEN CAST(mbpl AS INTEGER) / 100
                                                    ELSE CAST(mbpl AS INTEGER) END AS TEXT), '0')
                           FROM individuals
                           """)
            cursor.execute("""
                           INSERT
                           OR IGNORE INTO computed_fam_hashes (family_id, family_hash)
                           SELECT f.family_id,
                                  h.dem_hash || '-SP-' || COALESCE(s.dem_hash, 'NONE')
                           FROM families f
                                    JOIN computed_ind_hashes h ON f.head_histid = h.histid
                                    LEFT JOIN computed_ind_hashes s ON f.spouse_histid = s.histid
                           """)


# ==============================================================================
# INDEX OPTIMIZATION
# ==============================================================================
def build_indices(vault_dir, logger):
    """
    Builds database indices AFTER the bulk ingestion is complete.
    Creating indices before inserting 816 million rows dramatically slows down ingestion.
    """
    logger.info("Building indices for downstream queries... (This may take a while)")
    for filename in os.listdir(vault_dir):
        if SAMPLE_MODE:
            if filename != SAMPLE_DB_NAME: continue
        else:
            if not (filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename): continue

        db_path = os.path.join(vault_dir, filename)
        logger.info(f"  -> Indexing {filename}...")
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_individuals_parents ON individuals(father_histid, mother_histid);")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_individuals_names ON individuals(last_name, first_name);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_year_serial ON families(year, serial);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_family ON individuals(family_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_head ON families(head_histid);")
    logger.info("Indices built successfully!")


def main():
    # Build computed hashes and indices at the very end of the script
    build_computed_hashes(VAULT_DIR, main_logger)
    build_indices(VAULT_DIR, main_logger)


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging(logger_name="MAIN")
    VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
    main()
