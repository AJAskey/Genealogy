"""
File: Audit_HIK.py

Summary: A debugging tool for Full Traceability. Paste an HIK from your GEDCOM,
         and this script will print every census household that person 
         was ever a part of, decade by decade.
"""

import duckdb

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"

# Paste the Reference Number (HIK) from Family Tree Maker right here!
TARGET_HIK = "bnJZClWcRUHvYAVV3vlG7"

def main():
    if not TARGET_HIK:
        print("Please enter a TARGET_HIK at the top of the script!")
        return

    print(f"Connecting to Test Vault and Auditing HIK: {TARGET_HIK}\n")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    # This query finds every HISTID for the target, finds their households, 
    # and pulls everyone who lived with them.
    query = f"""
        WITH target_histids AS (
            SELECT UNNEST([histid_1850, histid_1860, histid_1870, histid_1880, 
                           histid_1900, histid_1910, histid_1920, histid_1930, 
                           histid_1940, histid_1950]) AS histid
            FROM cw.ipums_crosswalk
            WHERE HIK = '{TARGET_HIK}'
        ),
        target_households AS (
            SELECT DISTINCT YEAR, SERIAL
            FROM individuals i
            JOIN target_histids t ON UPPER(TRIM(i.HISTID)) = UPPER(TRIM(t.histid))
            WHERE t.histid IS NOT NULL AND LENGTH(TRIM(t.histid)) > 5
        )
        , cw_unpivoted AS (
            SELECT TRIM(histid_1850) AS histid, HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1850)) > 5
            UNION ALL SELECT TRIM(histid_1860), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1860)) > 5
            UNION ALL SELECT TRIM(histid_1870), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1870)) > 5
            UNION ALL SELECT TRIM(histid_1880), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1880)) > 5
            UNION ALL SELECT TRIM(histid_1900), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1900)) > 5
            UNION ALL SELECT TRIM(histid_1910), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1910)) > 5
            UNION ALL SELECT TRIM(histid_1920), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1920)) > 5
            UNION ALL SELECT TRIM(histid_1930), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1930)) > 5
            UNION ALL SELECT TRIM(histid_1940), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1940)) > 5
            UNION ALL SELECT TRIM(histid_1950), HIK FROM cw.ipums_crosswalk WHERE LENGTH(TRIM(histid_1950)) > 5
        )
        SELECT 
            i.YEAR, i.RELATE, 
            'Serial_' || i.SERIAL AS first_name, 
            COALESCE(vh.HIK, 'No_HIK') AS last_name, 
            i.AGE, i.SEX, i.HISTID
        FROM individuals i
        JOIN target_households th ON i.YEAR = th.YEAR AND i.SERIAL = th.SERIAL
        LEFT JOIN cw_unpivoted vh ON UPPER(TRIM(i.HISTID)) = UPPER(vh.histid)
        ORDER BY i.YEAR, i.SERIAL, TRY_CAST(i.PERNUM AS INTEGER);
    """

    results = con.execute(query).fetchall()

    if not results:
        print("No census records found for this HIK in the current Vault.")
        return

    current_year = None
    for row in results:
        year, relate, fname, lname, age, sex, histid = row
        if year != current_year:
            print(f"\n--- {year} CENSUS HOUSEHOLD ---")
            current_year = year
        
        rel_str = str(relate).ljust(20)
        name_str = f"{fname} {lname}".ljust(30)
        print(f"  {rel_str} | {name_str} | Age: {age} | Sex: {'M' if str(sex).strip()=='1' else 'F'} | ID: {histid}")

if __name__ == "__main__":
    main()