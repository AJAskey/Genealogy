import duckdb
import os
import sys

# Dynamically add the project paths for logging
script_dir = os.path.dirname(os.path.abspath(__file__))
python_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(python_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from utils import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
if os.name == 'nt':
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")

def main():
    logger = gen_logging.setup_logging('DuckHuntTest')
    logger.info("=====================================================================")
    logger.info("  V4 DUCK HUNT SMOKE TEST (BIOLOGICAL TRACKING)")
    logger.info("=====================================================================")

    con = duckdb.connect()

    # Attach SQLite Vaults in strictly READ_ONLY mode so we don't block Ella5
    years_attached = []
    for year in range(1850, 1940, 10):
        db_path = os.path.join(YEARLY_VAULT_DIR, f"YearVault_{year}.db")
        if os.path.exists(db_path):
            con.execute(f"ATTACH '{db_path}' AS vault_{year} (TYPE SQLITE, READ_ONLY);")
            years_attached.append(year)
            
    logger.info(f"Attached READ_ONLY vaults for years: {years_attached}")
    
    # Pick 10 raw biological profiles from the 1880 individuals table
    logger.info("\nExtracting 10 raw biological profiles from 1880 individuals table...")
    targets = con.execute("""
        SELECT birthyr, sex, raced, bpld, fbpl, mbpl 
        FROM vault_1880.individuals 
        WHERE birthyr IS NOT NULL
        LIMIT 10 OFFSET 500000;
    """).fetchall()

    # Create a temp table to hold our targets for fast, safe joining
    con.execute("DROP TABLE IF EXISTS temp_targets;")
    con.execute("""
        CREATE TEMP TABLE temp_targets (
            target_id INTEGER, 
            birthyr VARCHAR, sex VARCHAR, raced VARCHAR, 
            bpld VARCHAR, fbpl VARCHAR, mbpl VARCHAR
        )
    """)
    
    # Dictionary to store results for easy printing
    results = {}

    for idx, t in enumerate(targets):
        target_id = idx + 1
        con.execute("INSERT INTO temp_targets VALUES (?, ?, ?, ?, ?, ?, ?)", [target_id] + list(t))
        
        # Create a string representation for logging (e.g., 1850|1|100|42|42|42)
        bio_string = "|".join([str(x) for x in t])
        results[target_id] = {'bio_string': bio_string, 'counts': {}}

    # Do exactly ONE full table scan per decade against the RAW tables
    logger.info("\nCommencing Batch Scan directly against raw 'individuals' tables...")
    for year in years_attached:
        logger.info(f"  -> Scanning {year} individuals table for all 10 targets...")
        
        # Pre-1880 censuses did not record Parent Birthplaces. We must drop them from the match criteria.
        join_cond = "ON t.birthyr IS NOT DISTINCT FROM i.birthyr AND t.sex IS NOT DISTINCT FROM i.sex AND t.raced IS NOT DISTINCT FROM i.raced AND t.bpld IS NOT DISTINCT FROM i.bpld"
        if year >= 1880:
            join_cond += " AND t.fbpl IS NOT DISTINCT FROM i.fbpl AND t.mbpl IS NOT DISTINCT FROM i.mbpl"

        # Use DuckDB's LIST() function to grab the clone details so we can inspect them
        counts = con.execute(f"""
            SELECT t.target_id, 
                   COUNT(i.histid),
                   LIST(i.histid || ' (State: ' || COALESCE(f.stateicp, 'N/A') || ' | County: ' || COALESCE(f.countyicp, 'N/A') || ' | KidsByrSum: ' || COALESCE(CAST(f.kids_byr_sum AS VARCHAR), '0') || ')')
            FROM temp_targets t
            LEFT JOIN vault_{year}.individuals i {join_cond}
            LEFT JOIN vault_{year}.families f ON i.family_id = f.family_id
            GROUP BY t.target_id;
        """).fetchall()
        
        for target_id, count, clone_list in counts:
            results[target_id]['counts'][year] = count
            if 0 < count <= 20 and clone_list:
                results[target_id][f'clones_{year}'] = [c for c in clone_list if c is not None]

    # Print the final summary
    for target_id in sorted(results.keys()):
        bio_string = results[target_id]['bio_string']
        logger.info(f"\n--- Target {target_id}: Raw Biology [{bio_string}] ---")
        for year in years_attached:
            count = results[target_id]['counts'].get(year, 0)
            logger.info(f"  -> {year}: Found {count} matches")
            
            # Print the differentiating details for the clones!
            if 0 < count <= 20:
                clones = results[target_id].get(f'clones_{year}', [])
                for c in clones:
                    logger.info(f"       * Clone -> {c}")

if __name__ == "__main__":
    main()