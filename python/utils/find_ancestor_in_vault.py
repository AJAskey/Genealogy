"""
File: find_ancestor_in_vault.py
Summary: A utility to search the massive raw Census Vaults (like 1880) 
         for a specific known ancestor using SQL.
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

# --- Search Parameters (Fill these in with your Ancestor's details!) ---
SEARCH_YEAR = 1880  # Shifted to 1880
TARGET_FIRST_NAME = "Josiah"
TARGET_LAST_NAME = "Edgar"
TARGET_BIRTH_YEAR = 1878
TARGET_BIRTH_YEAR_TOLERANCE = 2  # +/- years to allow for Census age inaccuracies
TARGET_STATE = ""  # Temporarily disabled until we find the true column name
TARGET_COUNTY = "" # Temporarily disabled until we find the true column name

VAULT_FILE = os.path.join(NAMED_VAULT_DIR, f"NamedVault_{SEARCH_YEAR}.db")

def search_ancestor():
    if not os.path.exists(VAULT_FILE):
        print(f"Error: Vault file not found at {VAULT_FILE}")
        return

    print(f"Searching {SEARCH_YEAR} Vault for: {TARGET_FIRST_NAME} {TARGET_LAST_NAME} (b. ~{TARGET_BIRTH_YEAR})...")
    
    con = duckdb.connect()
    con.execute(f"ATTACH '{VAULT_FILE}' AS vault (TYPE SQLITE, READ_ONLY);")

    where_clauses = [
        f"UPPER(i.last_name) LIKE '%{TARGET_LAST_NAME.upper()}%'",
        f"UPPER(i.first_name) LIKE '%{TARGET_FIRST_NAME.upper()}%'",
        f"i.birthyr BETWEEN {TARGET_BIRTH_YEAR - BIRTH_YEAR_TOLERANCE} AND {TARGET_BIRTH_YEAR + BIRTH_YEAR_TOLERANCE}"
    ]

    if TARGET_STATE:
        where_clauses.append(f"UPPER(i.state) = '{TARGET_STATE.upper()}'")
    if TARGET_COUNTY:
        where_clauses.append(f"UPPER(i.county) LIKE '%{TARGET_COUNTY.upper()}%'")

    query = f"""
        SELECT
            i.histid,
            i.first_name,
            i.last_name,
            i.birthyr
        FROM vault.individuals i
        WHERE {' AND '.join(where_clauses)}
        LIMIT 20;
    """

    print("\n--- MATCHES FOUND ---")
    # duckdb's .show() will print a beautifully formatted table directly to the console
    con.execute(query).show()
    print("\nIf you see Josiah above, grab his 'histid'. We can use it to find his parents!")

if __name__ == '__main__':
    search_ancestor()