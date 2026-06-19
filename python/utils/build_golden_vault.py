"""
File: build_golden_vault.py
Summary: Creates microscopic "Golden Vaults" by extracting a specific, 
         known family (Clan) from the massive production vaults using 
         the Demographics DB as a map.
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
MATCH_DB = os.path.join(BASE_DATA_DIR, "DemographicMatches.db")
GOLDEN_VAULT_DIR = os.path.join(BASE_DATA_DIR, "GoldenVaults")

os.makedirs(GOLDEN_VAULT_DIR, exist_ok=True)

# The known longitudinal ID you want to extract
# You will need to query your DemographicMatches.db to find a valid clan_id first!
TARGET_CLAN_ID = 123456  # <-- UPDATE THIS to a real clan_id from your demographics DB

def build_golden_vault():
    print(f"Building Golden Vaults for Clan ID: {TARGET_CLAN_ID}...")
    
    con = duckdb.connect()
    
    if not os.path.exists(MATCH_DB):
        print(f"ERROR: Demographics DB not found at {MATCH_DB}")
        return
        
    con.execute(f"ATTACH '{MATCH_DB}' AS match_db (TYPE SQLITE, READ_ONLY);")
    
    for year in [1870, 1880, 1900]:
        source_db = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{year}.db")
        golden_db = os.path.join(GOLDEN_VAULT_DIR, f"NamedVault_{year}.db")
        
        if not os.path.exists(source_db):
            print(f"  -> Skipping {year}: Source vault not found.")
            continue
            
        if os.path.exists(golden_db):
            os.remove(golden_db)
            
        print(f"\nExtracting {year} records...")
        con.execute(f"ATTACH '{source_db}' AS source (READ_ONLY);")
        con.execute(f"ATTACH '{golden_db}' AS golden;")
        
        # 1. Grab the exact family record for this clan in this census year
        print("  -> Isolating target family...")
        con.execute(f"""
            CREATE TABLE golden.families AS 
            SELECT f.* 
            FROM source.families f
            JOIN match_db.clan_mapping c ON f.family_id = c.family_id
            WHERE c.clan_id = {TARGET_CLAN_ID};
        """)
        
        # 2. Grab the specific individuals (Head and Spouse) tied to that family
        print("  -> Isolating target individuals...")
        con.execute("""
            CREATE TABLE golden.individuals AS 
            SELECT i.* 
            FROM source.individuals i
            JOIN golden.families f ON (i.histid = f.head_histid OR i.histid = f.spouse_histid);
        """)
        
        con.execute("DETACH source;")
        con.execute("DETACH golden;")
        print(f"  -> SUCCESS: Golden vault saved at {golden_db}")

if __name__ == '__main__':
    build_golden_vault()