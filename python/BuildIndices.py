import os
import sqlite3
import sys

# Add the 'python' directory and project root to sys.path so we can import properly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
for p in [script_dir, project_root]:
    if p not in sys.path:
        sys.path.append(p)

from utils import gen_logging

if os.path.exists(r"C:\Data\Genealogy_Data\YearlyVaults"):
    VAULT_DIR = r"C:\Data\Genealogy_Data\YearlyVaults"
elif os.path.exists(r"D:\Data\Genealogy_Data\YearlyVaults"):
    VAULT_DIR = r"D:\Data\Genealogy_Data\YearlyVaults"
else:
    VAULT_DIR = r"C:\Data\Genealogy_Data\YearlyVaults"

def build_indices(vault_dir, logger):
    logger.info(f"Building indices for downstream queries in {vault_dir}... (This may take a while)")
    for filename in os.listdir(vault_dir):
        if not (filename.startswith("YearVault_") and filename.endswith(".db") and "Copy" not in filename): 
            continue

        db_path = os.path.join(vault_dir, filename)
        
        # Check if the file is read-only
        if not os.access(db_path, os.W_OK):
            logger.error(f"  [!] SKIP: {filename} is READ-ONLY. Please uncheck 'Read-only' in Windows properties!")
            continue

        logger.info(f"  -> Indexing {filename}...")
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_parents ON individuals(father_histid, mother_histid);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_names ON individuals(last_name, first_name);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_year_serial ON families(year, serial);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_individuals_family ON individuals(family_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_families_head ON families(head_histid);")
            logger.info(f"  -> {filename} indexed successfully!")
        except Exception as e:
            logger.error(f"  [!] ERROR indexing {filename}: {e}")

if __name__ == '__main__':
    logger = gen_logging.setup_logging(logger_name="INDEXER")
    build_indices(VAULT_DIR, logger)
    logger.info("Indexing complete.")