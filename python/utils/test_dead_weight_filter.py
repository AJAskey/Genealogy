"""
-----------------------------------
File: test_dead_weight_filter.py

Summary: Tests the DuckDB "Dead Weight" pre-filter against all Yearly Vaults
         using the exact list of 54 base BPL codes extracted from the GEDCOM.
         Proves the speed and elimination power of the SQL IN() clause.
-----------------------------------
"""
import glob
import os
import sys
import time

import duckdb

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
python_dir = os.path.join(project_root, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")

# The exact 54 unique location codes you extracted!
GEDCOM_BPL_CODES = [
    5, 6, 8, 9, 10, 11, 12, 13, 28, 400, 17, 18, 19, 404, 20, 150,
    23, 24, 25, 26, 411, 412, 27, 30, 414, 31, 410, 34, 36, 421,
    29, 39, 40, 425, 42, 41, 426, 45, 37, 47, 48, 49, 46, 51, 53,
    55, 56, 38, 453, 16, 401, 21, 22, 502
]


def test_filter(logger):
    logger.info("Initializing DuckDB Dead Weight Filter Test...")
    con = duckdb.connect()
    con.execute("INSTALL sqlite; LOAD sqlite;")

    vault_files = glob.glob(os.path.join(VAULT_DIR, "YearVault_*.db"))
    if not vault_files:
        logger.error("No YearVault databases found!")
        return

    union_queries = []
    for db_file in vault_files:
        year = os.path.basename(db_file).replace("YearVault_", "").replace(".db", "")
        alias = f"vault_{year}"

        try:
            con.execute(f"ATTACH '{db_file}' AS {alias} (TYPE SQLITE, READ_ONLY);")
            table_check = con.execute(
                f"SELECT count(*) FROM information_schema.tables WHERE table_catalog = '{alias}' AND table_name = 'individuals'").fetchone()[
                0]
            if table_check > 0:
                logger.info(f"  -> Attached {alias}")
                
                # DECISION: The "Married Couples Only" Filter!
                # Join against the families table to drop all children and unmarried adults.
                sql_query = f"""
                    SELECT i.bpld 
                    FROM {alias}.individuals i
                    JOIN {alias}.families f ON (i.histid = f.head_histid OR i.histid = f.spouse_histid)
                    WHERE f.head_histid IS NOT NULL AND f.spouse_histid IS NOT NULL
                      AND i.bpld IS NOT NULL AND i.bpld != ''
                """
                union_queries.append(sql_query)
        except Exception as e:
            logger.error(f"  -> Error attaching {db_file}: {e}")

    if not union_queries:
        logger.error("No individuals tables found.")
        return

    code_str = ", ".join(map(str, GEDCOM_BPL_CODES))

    query = f"""
        WITH all_census AS (
            {' UNION ALL '.join(union_queries)}
        )
        SELECT 
            COUNT(*) AS total_records,
            SUM(CASE 
                WHEN TRY_CAST(bpld AS INTEGER) IN ({code_str}) 
                  OR (TRY_CAST(bpld AS INTEGER) // 100) IN ({code_str}) 
                THEN 1 ELSE 0 END) AS surviving_records
        FROM all_census
    """

    logger.info(f"\nExecuting massive SQL IN() filter against {len(union_queries)} decades simultaneously...")
    start_time = time.time()

    result = con.execute(query).fetchone()
    total, surviving = result
    surviving = surviving or 0
    dropped = total - surviving

    elapsed = time.time() - start_time

    surviving_pct = (surviving / total) * 100 if total > 0 else 0.0
    dropped_pct = (dropped / total) * 100 if total > 0 else 0.0

    logger.info("==================================================")
    logger.info("       DEAD WEIGHT FILTER PERFORMANCE REPORT")
    logger.info("==================================================")
    logger.info(f" Execution Time      : {elapsed:.2f} seconds")
    logger.info(f" Total Census Records: {total:,}")
    logger.info(f" Surviving Targets   : {surviving:,} ({surviving_pct:.2f}%)")
    logger.info(f" Dropped Dead Weight : {dropped:,} ({dropped_pct:.2f}%)")
    logger.info("==================================================")
    logger.info("This proves exactly how many rows DuckDB will load into RAM ")
    logger.info("for the V2 Overlay before running the actual joins.")


if __name__ == '__main__':
    main_logger = gen_logging.setup_logging("DEAD_WEIGHT_TEST")
    test_filter(main_logger)
