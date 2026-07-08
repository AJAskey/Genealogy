"""
File: CreateTestCSV.py

Summary: Extracts a targeted "Golden Dataset" of a few thousand lines 
         from the massive Master Vault. It grabs specific "Key Players" 
         and automatically includes their entire households (Spouse/Children).
"""

import duckdb
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\test_census_subset.csv"

# Put the HISTIDs of your specific Key Players here!
# (e.g., Foster Askey's 1880 ID, his 1900 ID, etc.)
TARGET_HISTIDS = [
    # '8B06C466-9999-42CC-94DC-4AEF9B05316A',
]

def main():
    print(f"Connecting to Master Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    if TARGET_HISTIDS:
        print("Extracting Key Players and their full households...")
        histids_sql = ", ".join([f"'{h}'" for h in TARGET_HISTIDS])
        
        # This query finds the households of the targets, then selects EVERYONE in those households
        query = f"""
            COPY (
                WITH target_households AS (
                    SELECT DISTINCT YEAR, SERIAL 
                    FROM individuals 
                    WHERE HISTID IN ({histids_sql})
                )
                SELECT i.*
                FROM individuals i
                INNER JOIN target_households t 
                    ON i.YEAR = t.YEAR AND i.SERIAL = t.SERIAL
            ) TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',');
        """
    else:
        print("No targets provided. Extracting 500 random households (~2,500 lines)...")
        query = f"""
            COPY (
                SELECT * FROM individuals 
                WHERE SERIAL IN (SELECT SERIAL FROM families LIMIT 500)
            ) TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',');
        """

    con.execute(query)
    print(f"SUCCESS! Test file created at: {OUTPUT_CSV}")


if __name__ == '__main__':
    main()