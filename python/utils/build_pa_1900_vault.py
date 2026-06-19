"""
File: build_pa_1900_vault.py
Summary: Creates targeted databases containing ONLY couples born after 1900 
         from Pennsylvania, along with their children.
"""

import os
import duckdb

# --- Configuration ---
if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

NAMED_VAULT_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
NEW_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")
os.makedirs(NEW_VAULT_DIR, exist_ok=True)

def build_database_for_year(year):
    source_db = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{year}.db")
    target_db = os.path.join(NEW_VAULT_DIR, f"PA_1900_Couples_{year}.db")

    if not os.path.exists(source_db):
        print(f"Skipping {year}: Source database not found at {source_db}")
        return

    if os.path.exists(target_db):
        os.remove(target_db)

    print(f"\n========================================")
    print(f"Building PA Post-1900 Database for {year}...")
    
    con = duckdb.connect()
    con.execute(f"ATTACH '{source_db}' AS source (READ_ONLY);")
    con.execute(f"ATTACH '{target_db}' AS target;")

    print("1. Identifying PA Couples born after 1900...")
    # We use the household serial number to grab the couple AND their kids
    con.execute("""
        CREATE TEMP TABLE target_serials AS
        SELECT DISTINCT h.serial
        FROM source.families f
        JOIN source.individuals h ON f.head_histid = h.histid
        JOIN source.individuals s ON f.spouse_histid = s.histid
        WHERE h.birthyr >= 1900 AND s.birthyr >= 1900
          AND (h.bpld IN ('42', '4200') OR s.bpld IN ('42', '4200'));
    """)
    
    count = con.execute("SELECT COUNT(*) FROM target_serials").fetchone()[0]
    print(f"   -> Found {count:,} matching households.")

    print("2. Extracting Couples and their Kids...")
    con.execute("CREATE TABLE target.individuals AS SELECT i.* FROM source.individuals i JOIN target_serials ts ON i.serial = ts.serial;")

    print("3. Extracting Family links...")
    con.execute("CREATE TABLE target.families AS SELECT f.* FROM source.families f JOIN target.individuals h ON f.head_histid = h.histid;")

    con.close()
    print(f"Done! Database saved to: {target_db}")

if __name__ == '__main__':
    # 1920, 1930, and 1940 are the prime censuses for couples born after 1900 to have children
    for census_year in [1920, 1930, 1940]:
        build_database_for_year(census_year)