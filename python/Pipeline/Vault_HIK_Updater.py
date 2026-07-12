"""
File: Vault_HIK_Updater.py
Summary: Permanently adds the 'HIK' column directly to the 'individuals' table 
         in your master DuckDB Vault without having to re-ingest the CSV.
"""

import duckdb

# --- CONFIGURATION ---
VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db" 
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"

def add_hik_to_vault():
    print(f"Connecting to Vault: {VAULT_DB}")
    # Note: read_only=False because we are modifying the database!
    con = duckdb.connect(database=VAULT_DB, read_only=False)

    print("Attaching Crosswalk database...")
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    print("Unpivoting Crosswalk data into a temporary table (this may take a moment)...")
    con.execute("""
        CREATE TEMP TABLE cw_unpivoted AS
        SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1850)) > 5
        UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1860)) > 5
        UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1870)) > 5
        UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1880)) > 5
        UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1900)) > 5
        UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1910)) > 5
        UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1920)) > 5
        UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1930)) > 5
        UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1940)) > 5
        UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1950)) > 5;
    """)

    print("Merging HIKs and rewriting the 'individuals' table...")
    con.execute("""
        CREATE TABLE individuals_with_hik AS
        SELECT i.*, COALESCE(c.HIK, i.HISTID) AS HIK
        FROM individuals i
        LEFT JOIN cw_unpivoted c ON UPPER(TRIM(i.HISTID)) = UPPER(c.histid);
    """)

    print("Swapping tables to make the update permanent...")
    con.execute("DROP TABLE individuals;")
    con.execute("ALTER TABLE individuals_with_hik RENAME TO individuals;")

    print("🎉 Success! The 'individuals' table now permanently has an 'HIK' column.")

if __name__ == "__main__":
    add_hik_to_vault()