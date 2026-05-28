"""
-----------------------------------
File: export_subset_db.py

Summary: Creates a small, view-only SQLite database from the massive 
         Master Vault using a custom SQL filter. Since the Master Vault 
         already has all the IPUMS integer codes translated to text, 
         this script simply copies the filtered rows instantly.

Usage: Modify the TARGET_DB and SQL_FILTER variables, then run.
-----------------------------------
"""
import os
import duckdb
import gen_logging

# ==============================================================================
# CONFIGURATION
# ==============================================================================
MASTER_DB = r"D:\Data\Genealogy_Data\MasterVault_ALL.db"
TARGET_DB = r"D:\Data\Genealogy_Data\View_Pennsylvania.db"

# Put your custom SQL filter here! 
# Example: "stateicp = 'Pennsylvania' AND year = '1900'"
# Example: "namelast = 'ASKEY' AND namefrst = 'THOMAS'"
SQL_FILTER = "stateicp = 'Pennsylvania'"

def export_subset(logger):
    logger.info(f"Starting export to {os.path.basename(TARGET_DB)}...")
    
    # Connect to DuckDB in memory and set memory limits
    con = duckdb.connect(database=':memory:')
    con.execute("PRAGMA memory_limit='90GB';")
    
    # Load SQLite scanner
    con.execute("INSTALL sqlite;")
    con.execute("LOAD sqlite;")
    
    # Attach the massive Master Vault (Read Only)
    logger.info(f"Attaching Master Vault: {MASTER_DB}")
    con.execute(f"ATTACH '{MASTER_DB}' AS master (TYPE SQLITE, READ_ONLY);")
    
    # Delete the target DB if it already exists so we get a fresh copy
    if os.path.exists(TARGET_DB):
        os.remove(TARGET_DB)
        
    # Attach the brand new target SQLite database
    logger.info(f"Creating Target DB: {TARGET_DB}")
    con.execute(f"ATTACH '{TARGET_DB}' AS target (TYPE SQLITE);")
    
    # Run the blazing fast DuckDB transfer
    logger.info(f"Filtering Master Vault using: WHERE {SQL_FILTER}")
    logger.info("Executing transfer... this might take a minute or two.")
    
    con.execute(f"""
        CREATE TABLE target.population AS 
        SELECT * FROM master.population 
        WHERE {SQL_FILTER};
    """)
    
    # Get the final count
    count = con.execute("SELECT COUNT(*) FROM target.population").fetchone()[0]
    
    logger.info(f"Success! {count:,} records were written to {os.path.basename(TARGET_DB)}.")
    logger.info("You can now open this smaller database in DB Browser.")
    
    con.close()

if __name__ == "__main__":
    logger = gen_logging.setup_logging(logger_name="SUBSET")
    export_subset(logger)