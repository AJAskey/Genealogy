"""
File: build_test_vault.py
Summary: Shrinks massive production vaults into lightweight test vaults 
         by stripping out singles, childless couples, and dead weight.
"""

import os
import duckdb

# Setup paths
if os.path.exists(r"d:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"d:\Data\Genealogy_Data"
elif os.path.exists(r"D:\Data\Genealogy_Data"):
    BASE_DATA_DIR = r"D:\Data\Genealogy_Data"
else:
    BASE_DATA_DIR = os.path.expanduser("~/Genealogy_Data")

SOURCE_DIR = os.path.join(BASE_DATA_DIR, "NamedVaults")
TEST_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")

os.makedirs(TEST_DIR, exist_ok=True)

def build_test_vault(year):
    source_db = os.path.join(SOURCE_DIR, f"NamedVault_{year}.db")
    test_db = os.path.join(TEST_DIR, f"NamedVault_{year}.db")
    
    if not os.path.exists(source_db):
        print(f"Source vault {source_db} not found. Skipping...")
        return

    if os.path.exists(test_db):
        os.remove(test_db)
        
    print(f"\nBuilding Lightweight Test Vault for {year}...")
    con = duckdb.connect()
    con.execute(f"ATTACH '{source_db}' AS source (READ_ONLY);")
    con.execute(f"ATTACH '{test_db}' AS test;")
    
    print("  -> Extracting families (Married, > 0 kids)...")
    con.execute("CREATE TABLE test.families AS SELECT * FROM source.families WHERE head_histid IS NOT NULL AND spouse_histid IS NOT NULL AND num_kids > 0;")
    
    print("  -> Extracting relevant individuals...")
    con.execute("CREATE TABLE test.individuals AS SELECT i.* FROM source.individuals i JOIN test.families f ON i.histid = f.head_histid OR i.histid = f.spouse_histid;")
    
    con.close()
    print(f"  -> Done! Lean test vault created at: {test_db}")

if __name__ == '__main__':
    # Build test vaults for whichever years you want to test rapidly
    for test_year in [1870, 1880, 1900]:
        build_test_vault(test_year)