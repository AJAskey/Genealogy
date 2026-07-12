import duckdb
import os
import NameList

# --- CONFIGURATION ---
MASTER_VAULT_DB = r"d:\Data\Genealogy_Data\Master_DuckDB_Vault.db"
OUTPUT_CSV = r"C:\tempc\ShortTermCSVfiles\super_trackers_pa.csv"

dec_cnt = 5


def main():
    print(f"Connecting to Master Vault to extract CSV subset...")
    con = duckdb.connect(database=MASTER_VAULT_DB, read_only=True)

    # --- REGISTER PYTHON UDFs ---
    # This bridges the gap between Python and the Database!
    def get_random_surname(dummy_year: str, dummy_serial: str) -> str:
        # Grab the surname and clean up any trailing commas/spaces from the list
        return NameList.getNextSurname().replace(',', '').strip()

    def get_random_first(sex: str, dummy_histid: str) -> str:
        # IPUMS SEX code: '1' is Male, anything else (like '2') is Female
        if str(sex).strip() == '1':
            return NameList.getNextMale().replace(',', '').strip()
        return NameList.getNextFemale().replace(',', '').strip()

    con.create_function("get_random_surname", get_random_surname, [str, str], str)
    con.create_function("get_random_first", get_random_first, [str, str], str)

    print(f"Finding {dec_cnt}+ decade Key Players in Centre/Clearfield and surrounding Counties and writing to CSV...")

    # This query uses the crosswalk to find people with 5+ appearances,
    # filters them by county in the vault, and exports their households to a CSV.
    query = f"""
        COPY (
            WITH super_trackers AS (
                -- Since HIK is natively in the Vault now, we just find people who 
                -- appear in 5+ distinct census years!
                SELECT HIK 
                FROM individuals 
                WHERE HIK IS NOT NULL
                GROUP BY HIK 
                HAVING COUNT(DISTINCT YEAR) >= {dec_cnt}
            ),
            target_households AS (
                -- Find households using TRY_CAST to fix missing leading zero issues (e.g. '0270' vs '270')
                SELECT DISTINCT i.YEAR, i.SERIAL
                FROM individuals i
                JOIN families f ON i.YEAR = f.YEAR AND i.SERIAL = f.SERIAL
                WHERE i.HIK IN (SELECT HIK FROM super_trackers)
                  AND TRY_CAST(i.STATEICP AS INTEGER) = 14
                  AND TRY_CAST(i.COUNTYICP AS INTEGER) IN (270, 330, 230, 350, 470, 810, 630)
                  AND f.spouse_histid IS NOT NULL
                  AND f.num_kids > 0
                  
                  -- NEW FILTERS: 
                  -- 1. Filter by Occupation (e.g., OCC1950 code for sawmill/lumber workers)
                  -- AND TRY_CAST(i.OCC1950 AS INTEGER) = 683  
                  
                  -- Or look for multiple related occupation codes at once:
                  -- AND TRY_CAST(i.OCC1950 AS INTEGER) IN (683, 684, 536)
                  
                  -- 2. Filter by a Birth Year Range:
                  -- AND TRY_CAST(i.BIRTHYR AS INTEGER) BETWEEN 1880 AND 1890
                  
            ),
            named_households AS (
                -- Assign a unique, readable name to each household for easy tracking in the CSV
                SELECT
                    *,
                    get_random_surname(YEAR, SERIAL) AS fake_last_name
                FROM target_households
            )
            -- Finally, select ONLY the nuclear family (Head, Spouse, Kids)
            SELECT
                i.*,
                get_random_first(i.SEX, i.HISTID) AS NAMEFIRST,
                nh.fake_last_name AS NAMELAST
            FROM individuals i
            INNER JOIN named_households nh ON i.YEAR = nh.YEAR AND i.SERIAL = nh.SERIAL
            WHERE i.RELATE IN ('01', '1', 'Head/householder', '02', '2', 'Spouse', '03', '3', 'Child')
        ) TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',');
    """
    con.execute(query)
    print(f"SUCCESS! Extracted raw CSV file created at: {OUTPUT_CSV}")


if __name__ == '__main__':
    main()
