"""
File: build_pa_vault.py
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

YEARLY_VAULT_DIR = os.path.join(BASE_DATA_DIR, "YearlyVaults")
NEW_VAULT_DIR = os.path.join(BASE_DATA_DIR, "TestVaults")
os.makedirs(NEW_VAULT_DIR, exist_ok=True)

def get_source_db(year):
    """Finds the database file containing the year, regardless of the prefix."""
    if os.path.exists(YEARLY_VAULT_DIR):
        for filename in os.listdir(YEARLY_VAULT_DIR):
            if str(year) in filename and filename.endswith(".db"):
                return os.path.join(YEARLY_VAULT_DIR, filename)
    return None

def build_database_for_year(year):
    source_db = get_source_db(year)
    target_db = os.path.join(NEW_VAULT_DIR, f"PA_1900_Couples_{year}.db")

    if not source_db:
        print(f"Skipping {year}: No database found for {year} in {YEARLY_VAULT_DIR}")
        return

    if os.path.exists(target_db):
        os.remove(target_db)

    print(f"\n========================================")
    print(f"Building PA Post-1900 Database for {year}...")

    con = duckdb.connect()

    # Force DuckDB to read and write these as standard SQLite files
    con.execute("INSTALL sqlite; LOAD sqlite;")
    con.execute(f"ATTACH '{source_db}' AS source (TYPE SQLITE, READ_ONLY);")
    con.execute(f"ATTACH '{target_db}' AS target (TYPE SQLITE);")

    print("1. Identifying PA Couples born after 1900...")
    # We use the household serial number to grab the couple AND their kids
    con.execute("""
                CREATE
                TEMP TABLE target_serials AS
                SELECT DISTINCT h.serial
                FROM source.families f
                         JOIN source.individuals h ON f.head_histid = h.histid
                         JOIN source.individuals s ON f.spouse_histid = s.histid
                WHERE (h.birthyr >= 1900 OR s.birthyr >= 1900)
                  AND (h.bpld IN ('42', '4200') OR s.bpld IN ('42', '4200'));
                """)

    count = con.execute("SELECT COUNT(*) FROM target_serials").fetchone()[0]
    print(f"   -> Found {count:,} matching households.")

    print("2. Extracting Couples and their Kids (and adding Spouse Birthplace)...")
    # Create a mapping of every married person's histid to their spouse's bpld
    con.execute("""
        CREATE TEMP TABLE spouse_mapping AS
        SELECT f.head_histid AS histid, s.bpld AS spouse_bpld
        FROM source.families f
        JOIN source.individuals s ON f.spouse_histid = s.histid
        WHERE f.head_histid IS NOT NULL AND f.spouse_histid IS NOT NULL
        UNION
        SELECT f.spouse_histid AS histid, h.bpld AS spouse_bpld
        FROM source.families f
        JOIN source.individuals h ON f.head_histid = h.histid
        WHERE f.head_histid IS NOT NULL AND f.spouse_histid IS NOT NULL;
    """)

    con.execute("""
        CREATE TABLE target.individuals AS 
        SELECT i.*, sm.spouse_bpld
        FROM source.individuals i 
        JOIN target_serials ts ON i.serial = ts.serial
        LEFT JOIN spouse_mapping sm ON i.histid = sm.histid;
    """)

    print("3. Extracting Family links...")
    con.execute(
        "CREATE TABLE target.families AS SELECT f.* FROM source.families f JOIN target.individuals h ON f.head_histid = h.histid;")

    con.close()
    print(f"Done! Database saved to: {target_db}")


if __name__ == '__main__':
    # Starting with just 1920 to work out the kinks before hooking all three together
    for census_year in [1920]:
        build_database_for_year(census_year)
