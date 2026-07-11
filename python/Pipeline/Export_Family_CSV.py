"""
File: Export_Family_CSV.py

Summary: Extracts the multi-generational family data (including HIKs) 
         from the Vault and exports it into a highly readable, flat CSV file.
"""

import duckdb
import os

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Test_DuckDB_Vault.db"
CROSSWALK_DB = r"d:\Data\Genealogy_Data\IPUMS_Crosswalk.db"
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\family_rosters_with_hiks.csv"


def main():
    print(f"Connecting to Test Vault: {MASTER_VAULT_DB}...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    print("Attaching Crosswalk Time Machine...")
    con.execute(f"ATTACH '{CROSSWALK_DB}' AS cw (READ_ONLY);")

    print(f"Extracting Family Rosters to {OUTPUT_CSV}...")

    # This query links the individual to their HIK, and also links them to 
    # the HIK of the Head and Spouse of their current household.
    query = f"""
        COPY (
            WITH cw_unpivoted AS (
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
            ),
            vault_hiks AS (
                SELECT i.HISTID, c.HIK
                FROM individuals i
                LEFT JOIN cw_unpivoted c ON UPPER(TRIM(i.HISTID)) = UPPER(c.histid)
            )
            SELECT 
                i.YEAR, 
                i.SERIAL AS household_id,
                vh.HIK AS person_hik,
                CASE 
                    WHEN TRIM(i.RELATE) IN ('01', '1', 'Head/householder') THEN 'Head'
                    WHEN TRIM(i.RELATE) IN ('02', '2', 'Spouse') THEN 'Spouse'
                    WHEN TRIM(i.RELATE) IN ('03', '3', 'Child') THEN 'Child'
                    ELSE i.RELATE 
                END AS role,
                COUNT(i.YEAR) OVER (PARTITION BY vh.HIK) AS decades_present,
                i.NAMEFIRST AS first_name, -- Update to the actual first name column in your database
                i.NAMELAST AS last_name,   -- Verify this column name as well
                i.AGE, 
                CASE 
                    WHEN TRIM(i.SEX) = '1' THEN 'Male' 
                    WHEN TRIM(i.SEX) = '2' THEN 'Female' 
                    ELSE i.SEX 
                END AS sex,
                head_hik.HIK AS head_of_house_hik,
                spouse_hik.HIK AS spouse_of_house_hik
            FROM individuals i
            LEFT JOIN vault_hiks vh ON i.HISTID = vh.HISTID
            LEFT JOIN families f ON i.YEAR = f.YEAR AND i.SERIAL = f.SERIAL
            LEFT JOIN vault_hiks head_hik ON f.head_histid = head_hik.HISTID
            LEFT JOIN vault_hiks spouse_hik ON f.spouse_histid = spouse_hik.HISTID
            ORDER BY i.YEAR, i.SERIAL, TRY_CAST(i.PERNUM AS INTEGER)
        ) TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',');
    """
    
    try:
        con.execute(query)
        print("SUCCESS! CSV file is ready to read.")
    except duckdb.BinderException as e:
        print("\n" + "="*70)
        print("DATABASE ERROR: Could not find a column in your query.")
        print("Here are the ACTUAL columns that exist in your 'individuals' table:")
        print("="*70)
        columns = con.execute("DESCRIBE individuals").fetchall()
        for col in columns:
            print(f" - {col[0]}  ({col[1]})")
        print("="*70)
        print("ACTION REQUIRED:")
        print("1. Look at the list above to find the exact names of your first/last name columns.")
        print("2. Update 'i.NAMEFIRST' and 'i.NAMELAST' in your SQL query to match them.")
        print("3. If the names are completely missing from the list, you will need to update")
        print("   the pipeline script that builds Test_DuckDB_Vault.db to include them!")
        print("="*70 + "\n")
        raise e


if __name__ == "__main__":
    main()
